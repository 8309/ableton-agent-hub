from __future__ import annotations

import asyncio
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


XML = b'''<Ableton MajorVersion="5" Creator="Ableton Live test"><LiveSet>
<Tracks><MidiTrack Id="10"><Name><EffectiveName Value="Lead"/></Name>
<DeviceChain><MainSequencer><ClipTimeable><ArrangerAutomation><Events>
<MidiClip Id="20"><Name Value="Lead Phrase"/><CurrentStart Value="0"/><CurrentEnd Value="4"/>
<Loop><LoopStart Value="0"/><LoopEnd Value="4"/><StartRelative Value="0"/><LoopOn Value="false"/></Loop>
<Notes><KeyTracks><KeyTrack><MidiKey Value="60"/><Notes>
<MidiNoteEvent Time="0" Duration="1" Velocity="100" OffVelocity="64"/>
</Notes></KeyTrack></KeyTracks></Notes></MidiClip>
</Events></ArrangerAutomation></ClipTimeable></MainSequencer>
<DeviceChain><Devices><Eq8 Id="25"><UserName Value="Lead EQ"/>
<Band1Gain><Manual Value="0.5"/><AutomationTarget Id="101"/></Band1Gain></Eq8></Devices></DeviceChain></DeviceChain>
<AutomationEnvelopes><Envelopes><AutomationEnvelope Id="30"><EnvelopeTarget><PointeeId Value="101"/></EnvelopeTarget>
<Automation><Events><FloatEvent Time="0" Value="0.5"/><FloatEvent Time="8" Value="0.8"/></Events></Automation></AutomationEnvelope></Envelopes></AutomationEnvelopes>
</MidiTrack></Tracks>
<MainTrack><Name><EffectiveName Value="Main"/></Name><DeviceChain><Mixer><Tempo><Manual Value="132"/><AutomationTarget Id="8"/></Tempo></Mixer></DeviceChain>
<AutomationEnvelopes><Envelopes><AutomationEnvelope Id="31"><EnvelopeTarget><PointeeId Value="8"/></EnvelopeTarget>
<Automation><Events><FloatEvent Time="0" Value="132"/><FloatEvent Time="128" Value="120"/></Events></Automation></AutomationEnvelope></Envelopes></AutomationEnvelopes></MainTrack>
<Scenes><Scene Id="40"><Name Value="Intro"/></Scene></Scenes>
<GroovePool><Grooves><Groove Id="50"><Name Value="Swing"/></Groove></Grooves></GroovePool>
</LiveSet></Ableton>'''


class AlsBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "Song.als"
        self.path.write_bytes(gzip.compress(XML))

    def test_combines_old_readers_and_keeps_all_sections_bounded(self):
        from ableton_bridge.als_bundle import read_saved_set

        result = read_saved_set(self.path, include_midi_notes=True, midi_limit=8)

        self.assertTrue(result["ok"])
        self.assertTrue(result["read_only"])
        self.assertEqual(result["summary"]["track_count"], 1)
        self.assertEqual(result["summary"]["midi_clip_count"], 1)
        self.assertEqual(result["summary"]["returned_midi_note_count"], 1)
        self.assertEqual(result["summary"]["tempo_automation_envelope_count"], 1)
        self.assertEqual(result["scenes"][0]["name"], "Intro")
        self.assertEqual(result["grooves"]["items"][0]["name"], "Swing")
        self.assertEqual(result["midi"]["clips"][0]["notes"][0]["pitch"], 60)
        self.assertEqual(result["automation"]["tempo_envelopes"][0]["events"][1]["attributes"]["Time"], 128)
        self.assertTrue(result["cache"]["shared_document"])

    def test_snapshot_project_and_midi_share_parsed_document(self):
        from ableton_bridge.als_loader import clear_als_document_cache
        from ableton_bridge.als_midi import read_als_midi
        from ableton_bridge.als_project import read_als_project
        from ableton_bridge.als_snapshot import read_als_snapshot

        clear_als_document_cache()
        first = read_als_snapshot(self.path)
        second = read_als_project(self.path, sections={"tracks"})
        third = read_als_midi(self.path, include_notes=False)

        self.assertFalse(first["source"]["cache_hit"])
        self.assertTrue(second["source"]["cache_hit"])
        self.assertTrue(third["source"]["cache_hit"])
        self.assertEqual(first["source"]["file_token"], second["source"]["file_token"])
        self.assertEqual(second["source"]["file_token"], third["source"]["file_token"])

    def test_changed_saved_file_is_rejected_between_reads(self):
        from ableton_bridge.als_bundle import read_saved_set

        first = read_saved_set(self.path, sections={"tracks"})
        self.path.write_bytes(gzip.compress(XML.replace(b'Value="132"', b'Value="133"')))
        second = read_saved_set(self.path, sections={"tracks"})

        self.assertNotEqual(first["source"]["file_token"], second["source"]["file_token"])

    def test_mcp_saved_set_is_local_and_does_not_call_service(self):
        from mcp import Client
        import ableton_bridge.mcp_server as module

        async def exercise():
            with patch.object(module, "service") as service:
                async with Client(module.mcp, raise_exceptions=True) as client:
                    result = await client.call_tool(
                        "ableton_read_saved_set",
                        {"request": {"als_path": str(self.path), "sections": ["tracks"]}},
                    )
                    self.assertFalse(
                        result.is_error,
                        (result.structured_content, result.content),
                    )
                    self.assertTrue(result.structured_content["ok"])
                    service.assert_not_called()

        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
