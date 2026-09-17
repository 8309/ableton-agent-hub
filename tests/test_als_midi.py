from __future__ import annotations

import gzip
from pathlib import Path
import tempfile
import unittest


class AlsMidiTest(unittest.TestCase):
    def _write_set(self, directory: Path) -> Path:
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Ableton MajorVersion="5" MinorVersion="12.0_test" Creator="Ableton Live Test" Revision="abc">
  <LiveSet>
    <Tracks>
      <MidiTrack Id="10">
        <Name><UserName Value="Drums"/><EffectiveName Value="01 Drums"/></Name>
        <DeviceChain><MainSequencer><ClipTimeable><ArrangerAutomation><Events>
          <MidiClip Id="2">
            <LomId Value="200"/><CurrentStart Value="8"/><CurrentEnd Value="16"/>
            <Loop><LoopStart Value="0"/><LoopEnd Value="4"/><StartRelative Value="2"/><LoopOn Value="true"/></Loop>
            <Name Value="Beat A"/><Color Value="14"/>
            <Notes><KeyTracks>
              <KeyTrack Id="1"><Notes>
                <MidiNoteEvent Time="0" Duration="0.5" Velocity="100" OffVelocity="64" NoteId="1"/>
                <MidiNoteEvent Time="2" Duration="0.25" Velocity="90" OffVelocity="63" IsEnabled="false" NoteId="2"/>
              </Notes><MidiKey Value="60"/></KeyTrack>
            </KeyTracks></Notes>
          </MidiClip>
          <MidiClip Id="3">
            <LomId Value="201"/><CurrentStart Value="16"/><CurrentEnd Value="20"/>
            <Loop><LoopStart Value="0"/><LoopEnd Value="4"/><StartRelative Value="0"/><LoopOn Value="false"/></Loop>
            <Name Value="Beat B"/><Color Value="15"/>
            <Notes><KeyTracks>
              <KeyTrack Id="2"><Notes><MidiNoteEvent Time="1" Duration="1" Velocity="80" OffVelocity="64" NoteId="3"/></Notes><MidiKey Value="62"/></KeyTrack>
            </KeyTracks></Notes>
          </MidiClip>
        </Events></ArrangerAutomation></ClipTimeable></MainSequencer></DeviceChain>
      </MidiTrack>
    </Tracks>
    <GroovePool><Grooves><Groove><Clip><Value><MidiClip Id="99"><Name Value="Internal Groove"/></MidiClip></Value></Clip></Groove></Grooves></GroovePool>
  </LiveSet>
</Ableton>'''
        path = directory / "Song.als"
        path.write_bytes(gzip.compress(xml))
        return path

    def test_reads_arrangement_notes_and_expands_loop_occurrences(self):
        from ableton_bridge.als_midi import read_als_midi

        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_set(Path(temp_dir))
            before = path.read_bytes()
            result = read_als_midi(path, track_name="01 Drums", clip_name="Beat A")

            self.assertEqual(result["read"]["matched_clip_count"], 1)
            clip = result["clips"][0]
            self.assertEqual(clip["stored_note_count"], 2)
            self.assertEqual(clip["notes"][0]["arrangement_occurrences"], [10.0, 14.0])
            self.assertEqual(clip["notes"][1]["arrangement_occurrences"], [8.0, 12.0])
            self.assertEqual(clip["notes"][1]["mute"], 1)
            self.assertEqual(clip["notes"][1]["off_velocity"], 63.0)
            self.assertEqual(path.read_bytes(), before)

    def test_filters_and_pages_clips_without_including_groove_pool(self):
        from ableton_bridge.als_midi import read_als_midi

        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_set(Path(temp_dir))
            first = read_als_midi(path, limit=1, include_notes=False)
            second = read_als_midi(path, cursor=1, limit=1, include_notes=False)

            self.assertEqual(first["read"]["matched_clip_count"], 2)
            self.assertTrue(first["read"]["has_more"])
            self.assertEqual(first["clips"][0]["clip_name"], "Beat A")
            self.assertEqual(second["clips"][0]["clip_name"], "Beat B")
            self.assertFalse(second["read"]["has_more"])

    def test_note_and_occurrence_outputs_are_bounded(self):
        from ableton_bridge.als_midi import read_als_midi

        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_set(Path(temp_dir))
            result = read_als_midi(
                path,
                clip_name="Beat A",
                max_notes_per_clip=1,
                max_occurrences_per_clip=1,
            )
            clip = result["clips"][0]

            self.assertEqual(clip["returned_note_count"], 1)
            self.assertTrue(clip["notes_has_more"])
            self.assertEqual(len(clip["notes"][0]["arrangement_occurrences"]), 1)
            self.assertTrue(clip["occurrences_partial"])


if __name__ == "__main__":
    unittest.main()
