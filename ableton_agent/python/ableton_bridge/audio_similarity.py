"""Bounded local waveform evidence and explainable, non-semantic ranking."""
from __future__ import annotations

import json
from contextlib import closing
import math
from pathlib import Path
import sqlite3
import time

VERSION = "waveform-v1-block2048-30s"
SCHEMA = """CREATE TABLE IF NOT EXISTS waveform_cache (
    path TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, version TEXT NOT NULL,
    result_json TEXT NOT NULL)"""


def preserve_cache(destination: sqlite3.Connection, source: Path) -> None:
    destination.execute(SCHEMA)
    if not source.is_file():
        return
    with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as old:
        if old.execute("SELECT 1 FROM sqlite_master WHERE name='waveform_cache'").fetchone():
            destination.executemany("INSERT INTO waveform_cache VALUES (?,?,?,?)",
                                    old.execute("SELECT * FROM waveform_cache"))


def analyze(path: str | Path, database: str | Path, *, deadline: float | None = None) -> dict:
    source = Path(path).expanduser().resolve()
    base = {"path": str(source), "analysis_version": VERSION, "cache_hit": False}
    if not source.is_file():
        return {**base, "status": "skipped", "reason": "file_missing"}
    if source.suffix.lower() not in {".wav", ".aif", ".aiff", ".aifc", ".flac"}:
        return {**base, "status": "skipped", "reason": "unsupported_format"}
    if not Path(database).is_file():
        return {**base, "status": "skipped", "reason": "catalog_missing"}
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        return {**base, "status": "skipped", "reason": "install_audio_dependencies"}
    stat = source.stat()
    fingerprint = f"{stat.st_size}:{stat.st_mtime_ns}"
    version = f"{VERSION}:{np.__version__}:{sf.__version__}:{sf.__libsndfile_version__}"
    with closing(sqlite3.connect(database, timeout=2)) as db, db:
        db.execute(SCHEMA)
        cached = db.execute("SELECT result_json FROM waveform_cache WHERE path=? AND fingerprint=? AND version=?",
                            (str(source), fingerprint, version)).fetchone()
        if cached:
            return {**json.loads(cached[0]), "cache_hit": True}
    deadline = min(deadline, time.monotonic() + 10) if deadline else time.monotonic() + 10
    try:
        with sf.SoundFile(source) as audio:
            rate, channels = audio.samplerate, audio.channels
            if not 1 <= channels <= 8 or not 8000 <= rate <= 192000:
                return {**base, "status": "skipped", "reason": "unsupported_rate_or_channels"}
            count = min(audio.frames, rate * 30)
            frames = 0
            peak = energy = centroid_sum = flatness_sum = 0.0
            spectral_frames = attacks = 0
            previous_rms = 0.0
            last_attack = -rate
            window = np.hanning(2048)[:, None]
            frequencies = np.fft.rfftfreq(2048, 1 / rate)
            while frames < count:
                if time.monotonic() > deadline:
                    return {**base, "status": "skipped", "reason": "analysis_budget_exceeded"}
                block = audio.read(min(2048, count - frames), dtype="float64", always_2d=True)
                if not len(block):
                    break
                if not np.isfinite(block).all():
                    raise ValueError("non-finite audio samples")
                peak = max(peak, float(np.max(np.abs(block))))
                energy += float(np.sum(block * block))
                rms = float(np.sqrt(np.mean(block * block)))
                if rms > max(0.0001, previous_rms * 1.8) and frames - last_attack >= rate * 0.05:
                    attacks += 1
                    last_attack = frames
                previous_rms = rms
                padded = np.zeros((2048, channels))
                padded[:len(block)] = block
                # Average channel power, not samples: opposite phases must not cancel.
                power = np.mean(np.abs(np.fft.rfft(padded * window, axis=0)) ** 2, axis=1)
                if float(power.sum()) > 1e-16:
                    centroid_sum += float(np.sum(frequencies * power) / power.sum())
                    flatness_sum += float(np.exp(np.mean(np.log(np.maximum(power, 1e-20)))) / max(np.mean(power), 1e-20))
                    spectral_frames += 1
                frames += len(block)
            if not frames:
                raise ValueError("empty audio")
            result = {**base, "status": "ok", "sample_rate": rate, "channels": channels,
                      "duration_seconds": audio.frames / rate, "analyzed_start_seconds": 0,
                      "analyzed_seconds": frames / rate, "partial_file": frames < audio.frames,
                      "sample_peak": peak, "rms": math.sqrt(energy / (frames * channels)),
                      "spectral_centroid_hz": centroid_sum / spectral_frames if spectral_frames else None,
                      "spectral_flatness": flatness_sum / spectral_frames if spectral_frames else None,
                      "transient_density_hz": attacks / (frames / rate),
                      "transient_method": "block_rms_rise_1.8_refractory_50ms",
                      "decoder": version}
        after = source.stat()
        if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
            return {**base, "status": "skipped", "reason": "file_changed_during_analysis"}
        with closing(sqlite3.connect(database, timeout=2)) as db, db:
            db.execute("INSERT OR REPLACE INTO waveform_cache VALUES (?,?,?,?)",
                       (str(source), fingerprint, version, json.dumps(result, allow_nan=False)))
        return result
    except (RuntimeError, ValueError, OSError) as error:
        return {**base, "status": "skipped", "reason": "decode_failed", "error": str(error)}


def _vector(item):
    if item.get("spectral_centroid_hz") is None:
        return None
    return {
        "duration_seconds": math.log1p(item["duration_seconds"]) / math.log(31),
        "sample_peak": max(-120, 20 * math.log10(max(item["sample_peak"], 1e-6))) / 60,
        "rms": max(-120, 20 * math.log10(max(item["rms"], 1e-6))) / 60,
        "spectral_centroid_hz": math.log(max(item["spectral_centroid_hz"], 20) / 20) / math.log(1000),
        "spectral_flatness": item["spectral_flatness"],
        "transient_density_hz": math.log1p(item["transient_density_hz"]) / math.log(41),
    }


def rank_sounds(database, reference_audio, *, limit=5, candidate_limit=24, **filters):
    from .sound_catalog_db import search_database
    if not 1 <= limit <= 20 or not limit <= candidate_limit <= 64:
        raise ValueError("Require 1 <= limit <= 20 and limit <= candidate_limit <= 64")
    if filters.get("kind") not in (None, "audio_sample"):
        raise ValueError("Reference-audio ranking supports audio_sample only")
    deadline = time.monotonic() + 25
    ref = analyze(reference_audio, database, deadline=deadline)
    vector = _vector(ref) if ref["status"] == "ok" else None
    if vector is None:
        return {"ok": False, "error": "Reference has no usable waveform features", "reference": ref}
    filters["kind"] = "audio_sample"
    rows = search_database(database, limit=candidate_limit + 1, **filters)
    limited = len(rows) > candidate_limit
    good, skipped = [], []
    for row in rows[:candidate_limit]:
        if Path(row["path"]).resolve() == Path(ref["path"]):
            continue
        feature = analyze(row["path"], database, deadline=deadline)
        values = _vector(feature) if feature["status"] == "ok" else None
        if values is None:
            skipped.append({"path": row["path"], "reason": feature.get("reason", "silent_or_no_spectrum")})
            continue
        differences = {key: abs(values[key] - vector[key]) for key in vector}
        distance = math.sqrt(sum(x * x for x in differences.values()) / len(differences))
        reasons = [{"feature": key, "reference": ref[key], "candidate": feature[key],
                    "normalized_difference": differences[key]} for key in sorted(differences, key=differences.get)[:3]]
        good.append({**row, "exists": True, "feature_distance": distance, "similarity_reasons": reasons,
                     "waveform": feature})
    good.sort(key=lambda item: (item["feature_distance"], item["path"]))
    # Recheck immediately before returning paths; no loading or playback.
    existing = []
    for item in good:
        if Path(item["path"]).is_file():
            existing.append(item)
        else:
            skipped.append({"path": item["path"], "reason": "file_missing"})
    return {"ok": True, "read_only_live": True, "local_cache_updated": True,
            "reference": ref, "resources": existing[:limit], "unranked": skipped,
            "candidate_count": min(len(rows), candidate_limit), "candidate_limit": candidate_limit,
            "candidate_pool_truncated": limited, "scope": "filtered catalog order, bounded candidate pool",
            "metric": "fixed-scale RMS feature distance; lower is closer, not a quality score",
            "warning": "First 30 seconds only. Sample peak/RMS, not true peak/LUFS. Manual loading required."}
