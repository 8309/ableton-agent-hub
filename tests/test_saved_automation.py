import asyncio
import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ableton_bridge.saved_automation import SavedAutomationReader, parse_saved_curves

XML = b'''<Ableton Creator="Ableton Live test"><LiveSet><Tracks><AudioTrack Id="7">
<Name><EffectiveName Value="Lead"/></Name><DeviceChain><Devices><Eq8 Id="25">
<UserName Value="Lead EQ"/><Gain><Manual Value="0.5"/><AutomationTarget Id="101"/></Gain>
</Eq8></Devices></DeviceChain><AutomationEnvelopes><Envelopes><AutomationEnvelope Id="1">
<EnvelopeTarget><PointeeId Value="101"/></EnvelopeTarget><Automation><Events>
<FloatEvent Time="-63072000" Value="0.5"/><FloatEvent Time="0" Value="0.5"/>
<FloatEvent Time="128" Value="0.8" CurveControl1X="0.3"/>
<FloatEvent Time="144" Value="0.2"/><FloatEvent Time="144" Value="0.4"/>
</Events></Automation></AutomationEnvelope></Envelopes></AutomationEnvelopes>
<MidiClip><Envelopes><Envelopes><ClipEnvelope Id="9"/></Envelopes></Envelopes></MidiClip>
</AudioTrack><ReturnTrack Id="8"><Name><EffectiveName Value="A"/></Name></ReturnTrack>
</Tracks><MainTrack><DeviceChain><Mixer><Tempo><Manual Value="132"/>
<AutomationTarget Id="99"/></Tempo></Mixer></DeviceChain><AutomationEnvelopes><Envelopes>
<AutomationEnvelope Id="2"><EnvelopeTarget><PointeeId Value="99"/></EnvelopeTarget>
<Automation><Events><FloatEvent Time="0" Value="132"/><FloatEvent Time="128" Value="120"/>
</Events></Automation></AutomationEnvelope></Envelopes></AutomationEnvelopes></MainTrack>
</LiveSet></Ableton>'''


class SavedAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "Saved.als"
        self.path.write_bytes(gzip.compress(XML))
        self.reader = SavedAutomationReader()

    def read(self, **fields):
        return self.reader.read(dict(als_path=str(self.path), **fields))

    def test_list_mapping_and_readonly(self):
        before = self.path.read_bytes()
        result = self.read()
        self.assertEqual(result["total_items"], 2)
        self.assertFalse(result["source"]["live_verified"])
        self.assertEqual(result["items"][0]["target"]["device_path"][0]["type"], "Eq8")
        self.assertEqual(result["items"][1]["section"], "main")
        self.assertEqual(result["items"][0]["first_node"]["beat"], 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_points_range_bars_curvature_and_boundary_context(self):
        result = self.read(envelope_key="0:0", start_beat=128, end_beat=144)
        self.assertEqual([r["beat"] for r in result["items"]], [128, 144, 144])
        self.assertEqual(result["items"][0]["bar_reference"], 33)
        self.assertEqual(result["items"][0]["raw_attributes"]["CurveControl1X"], "0.3")
        self.assertEqual(result["preceding_node"]["beat"], 0)
        self.assertTrue(result["items"][1]["value_changes_to_next"])
        self.assertIsNone(result["curve_end_beat"])
        empty = self.read(envelope_key="0:0", start_beat=10, end_beat=20)
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["preceding_node"]["beat"], 0)
        self.assertEqual(empty["following_node"]["beat"], 128)

    def test_cached_pagination_and_stale_file(self):
        first = self.read(envelope_key="0:0", limit=2)
        with patch("ableton_bridge.saved_automation.parse_saved_curves", side_effect=AssertionError("reparsed")):
            second = self.read(envelope_key="0:0", limit=2, **first["continuation"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(len(first["items"] + second["items"]), 4)
        self.path.write_bytes(gzip.compress(XML.replace(b'Value="0.8"', b'Value="0.81"')))
        with self.assertRaisesRegex(ValueError, "stale_file"):
            self.read(envelope_key="0:0", **first["continuation"])

    def test_validation_and_bounds(self):
        for fields in (dict(limit=0), dict(cursor=1), dict(start_beat=5, end_beat=1), dict(envelope_key="unknown")):
            with self.assertRaises(ValueError):
                self.read(**fields)
        self.reader.MAX_XML = 5
        self.reader.cached = None
        with self.assertRaisesRegex(ValueError, "64 MiB"):
            self.read()
        with self.assertRaises(ValueError):
            self.reader.read(dict(als_path="relative.als"))

    def test_missing_target_and_unknown_events_are_not_claimed_complete(self):
        self.path.write_bytes(gzip.compress(XML.replace(b'PointeeId Value="101"', b'PointeeId Value="404"')
            .replace(b'<FloatEvent Time="128"', b'<UnknownEvent Time="128"')))
        result = self.read(envelope_key="0:0")
        self.assertFalse(result["curve_parse_complete"])
        self.assertIsNone(result["envelope"]["target"])
        self.assertGreaterEqual(len(result["envelope"]["warnings"]), 2)

    def test_dtd_and_not_a_set_rejected(self):
        for xml in (b'<!DOCTYPE x><Ableton/>', b'<Other/>', b'\x00<Ableton/>'):
            with self.assertRaises(ValueError):
                parse_saved_curves(xml)

    def test_initialization_not_reported_as_negative_bar(self):
        result = self.read(envelope_key="0:0", end_beat=0)
        self.assertEqual(result["preceding_node"]["beat"], -63072000)
        self.assertIsNone(result["preceding_node"]["bar_reference"])
        result = self.read(envelope_key="0:0", start_beat=128, end_beat=128, beats_per_bar=3)
        self.assertAlmostEqual(result["items"][0]["bar_reference"], 1+128/3)

    def test_mcp_local_only_dispatch(self):
        from mcp import Client
        import ableton_bridge.mcp_server as module
        async def exercise():
            with patch.object(module, "service") as service:
                async with Client(module.mcp, raise_exceptions=True) as client:
                    result = await client.call_tool("ableton_read_saved_automation", {"request":{"als_path":str(self.path)}})
                    self.assertFalse(result.is_error)
                    self.assertTrue(result.structured_content["ok"])
                service.assert_not_called()
                self.assertEqual(service.mock_calls, [])
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
