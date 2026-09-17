from __future__ import annotations

import gzip
from pathlib import Path
import tempfile
import unittest


XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<Ableton MajorVersion="5" MinorVersion="12.0_test" Creator="Ableton Live Test" Revision="abc">
  <LiveSet>
    <Tracks>
      <MidiTrack Id="10">
        <LomId Value="100"/><Name><UserName Value="Lead"/><EffectiveName Value="01 Lead"/></Name>
        <Color Value="12"/><TrackGroupId Value="-1"/><TrackUnfolded Value="true"/>
        <DeviceChain>
          <AudioInputRouting><Target Value="AudioIn/None"/><UpperDisplayString Value="None"/><LowerDisplayString Value=""/></AudioInputRouting>
          <MidiInputRouting><Target Value="MidiIn/External.All/-1"/><UpperDisplayString Value="All Ins"/><LowerDisplayString Value=""/></MidiInputRouting>
          <AudioOutputRouting><Target Value="AudioOut/Main"/><UpperDisplayString Value="Main"/><LowerDisplayString Value=""/></AudioOutputRouting>
          <MidiOutputRouting><Target Value="MidiOut/None"/><UpperDisplayString Value="None"/><LowerDisplayString Value=""/></MidiOutputRouting>
          <Mixer>
            <IsFolded Value="false"/><SoloSink Value="true"/><PanMode Value="0"/>
            <Speaker><Manual Value="true"/><AutomationTarget Id="2"/></Speaker>
            <Pan><Manual Value="0.25"/><MidiControllerRange><Min Value="-1"/><Max Value="1"/></MidiControllerRange><AutomationTarget Id="3"/></Pan>
            <Volume><Manual Value="0.8"/><AutomationTarget Id="4"/></Volume>
            <Sends><TrackSendHolder Id="0"><Send><Manual Value="0.1"/><AutomationTarget Id="5"/></Send><EnabledByUser Value="true"/></TrackSendHolder></Sends>
          </Mixer>
          <MainSequencer>
            <MonitoringEnum Value="1"/>
            <ClipSlotList><ClipSlot Id="0"><LomId Value="500"/><ClipSlot><Value><MidiClip Id="1">
              <LomId Value="501"/><CurrentStart Value="0"/><CurrentEnd Value="4"/>
              <Loop><LoopStart Value="0"/><LoopEnd Value="4"/><StartRelative Value="0"/><LoopOn Value="true"/></Loop>
              <Name Value="Session Lead"/><Color Value="9"/><LaunchMode Value="1"/><LaunchQuantisation Value="2"/>
              <Envelopes><Envelopes><ClipEnvelope Id="3"><EnvelopeTarget><PointeeId Value="20"/></EnvelopeTarget><Automation><Events><FloatEvent Id="1" Time="0" Value="1"/></Events></Automation></ClipEnvelope></Envelopes></Envelopes>
              <GrooveSettings><GrooveId Value="7"/></GrooveSettings><Disabled Value="false"/><VelocityAmount Value="2"/>
              <FollowAction><FollowTime Value="4"/><LoopIterations Value="2"/><FollowActionA Value="1"/><FollowActionB Value="0"/><FollowChanceA Value="80"/><FollowChanceB Value="20"/><JumpIndexA Value="1"/><JumpIndexB Value="2"/><FollowActionEnabled Value="true"/></FollowAction>
              <Notes><KeyTracks><KeyTrack><Notes><MidiNoteEvent Time="0" Duration="1" Velocity="90" OffVelocity="60" NoteId="2" Probability="0.75" VelocityDeviation="4"/></Notes><MidiKey Value="64"/></KeyTrack></KeyTracks>
                <PerNoteEventStore><EventLists><PerNoteEventList NoteId="2"><PerNoteEvent Time="0" Value="0.5"/></PerNoteEventList></EventLists></PerNoteEventStore>
                <NoteProbabilityGroups><NoteProbabilityGroup Id="1"><Probability Value="0.6"/></NoteProbabilityGroup></NoteProbabilityGroups>
              </Notes>
            </MidiClip></Value></ClipSlot><HasStop Value="true"/></ClipSlot></ClipSlotList>
          </MainSequencer>
          <DeviceChain><Devices><Eq8 Id="0"><LomId Value="600"/><On><Manual Value="true"/><AutomationTarget Id="20"/></On><IsFolded Value="false"/><UserName Value="Lead EQ"/><Band1Gain><Manual Value="1.5"/><MidiControllerRange><Min Value="-15"/><Max Value="15"/></MidiControllerRange><AutomationTarget Id="21"/></Band1Gain></Eq8></Devices></DeviceChain>
        </DeviceChain>
        <AutomationEnvelopes><Envelopes><AutomationEnvelope Id="1"><EnvelopeTarget><PointeeId Value="21"/></EnvelopeTarget><Automation><Events><FloatEvent Id="1" Time="0" Value="0"/><FloatEvent Id="2" Time="8" Value="3"/></Events></Automation></AutomationEnvelope></Envelopes></AutomationEnvelopes>
      </MidiTrack>
      <AudioTrack Id="11">
        <Name><EffectiveName Value="02 Texture"/></Name><Color Value="6"/><TrackGroupId Value="-1"/><TrackUnfolded Value="false"/>
        <DeviceChain><Mixer><Speaker><Manual Value="true"/></Speaker><SoloSink Value="false"/><Pan><Manual Value="0"/></Pan><Volume><Manual Value="1"/></Volume></Mixer>
          <MainSequencer><Sample><ArrangerAutomation><Events><AudioClip Id="4"><LomId Value="700"/><CurrentStart Value="8"/><CurrentEnd Value="12"/><Loop><LoopStart Value="0"/><LoopEnd Value="4"/><StartRelative Value="0"/><LoopOn Value="false"/></Loop><Name Value="Air"/><Color Value="5"/><LaunchMode Value="0"/><LaunchQuantisation Value="0"/><GrooveSettings><GrooveId Value="-1"/></GrooveSettings><FollowAction><FollowActionEnabled Value="false"/></FollowAction><SampleRef><FileRef><Path Value="C:/missing/air.wav"/><RelativePath Value="Samples/air.wav"/><OriginalFileSize Value="123"/></FileRef></SampleRef><IsWarped Value="true"/><WarpMode Value="0"/><PitchCoarse Value="-2"/><PitchFine Value="3"/><SampleVolume Value="0.9"/><Fades><FadeInLength Value="0.1"/><FadeOutLength Value="0.2"/></Fades><WarpMarkers><WarpMarker Id="0" SecTime="0" BeatTime="0"/><WarpMarker Id="1" SecTime="2" BeatTime="4"/></WarpMarkers><Envelopes><Envelopes/></Envelopes></AudioClip></Events></ArrangerAutomation></Sample></MainSequencer>
          <DeviceChain><Devices/></DeviceChain></DeviceChain>
      </AudioTrack>
    </Tracks>
    <MainTrack><Name><EffectiveName Value="Main"/></Name><DeviceChain><Mixer><Speaker><Manual Value="true"/></Speaker><SoloSink Value="false"/><Pan><Manual Value="0"/></Pan><Volume><Manual Value="1"/></Volume><Tempo><Manual Value="132"/><AutomationTarget Id="8"/></Tempo></Mixer><DeviceChain><Devices/></DeviceChain></DeviceChain><AutomationEnvelopes><Envelopes><AutomationEnvelope Id="2"><EnvelopeTarget><PointeeId Value="8"/></EnvelopeTarget><Automation><Events><FloatEvent Id="3" Time="0" Value="132"/><FloatEvent Id="4" Time="128" Value="120"/></Events></Automation></AutomationEnvelope></Envelopes></AutomationEnvelopes></MainTrack>
    <Scenes><Scene Id="0"><LomId Value="800"/><Name Value="Intro"/><Annotation Value=""/><Color Value="3"/><Tempo Value="128"/><IsTempoEnabled Value="true"/><TimeSignatureId Value="201"/><IsTimeSignatureEnabled Value="false"/><FollowAction><FollowActionEnabled Value="false"/></FollowAction></Scene></Scenes>
    <GroovePool><Grooves><Groove Id="7"><LomId Value="900"/><Name Value="Swing"/><Grid Value="3"/><QuantizationAmount Value="0"/><TimingAmount Value="66"/><RandomAmount Value="2"/><VelocityAmount Value="5"/></Groove></Grooves><DefaultGrooveId Value="7"/></GroovePool>
  </LiveSet>
</Ableton>'''


class AlsProjectTest(unittest.TestCase):
    def _write_set(self, directory: Path) -> Path:
        path = directory / "Project.als"
        path.write_bytes(gzip.compress(XML))
        return path

    def test_reads_tracks_mixer_routing_devices_and_parameters(self):
        from ableton_bridge.als_project import read_als_project

        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_set(Path(temp_dir))
            before = path.read_bytes()
            result = read_als_project(path, include_device_parameters=True)

            lead = result["tracks"][0]
            self.assertEqual(lead["routing"]["audio_output"]["upper_display"], "Main")
            self.assertEqual(lead["mixer"]["volume"]["internal_value"], 0.8)
            self.assertTrue(lead["mixer"]["saved_solo"])
            self.assertEqual(lead["mixer"]["sends"][0]["send"]["internal_value"], 0.1)
            eq = lead["devices"][0]
            self.assertEqual(eq["device_type"], "Eq8")
            self.assertEqual(eq["parameters"]["items"][1]["name"], "Band1Gain")
            self.assertIsNone(eq["plugin"])
            self.assertEqual(path.read_bytes(), before)

    def test_reads_scenes_audio_warp_automation_and_grooves(self):
        from ableton_bridge.als_project import read_als_project

        with tempfile.TemporaryDirectory() as temp_dir:
            result = read_als_project(self._write_set(Path(temp_dir)))

            self.assertEqual(result["scenes"][0]["name"], "Intro")
            audio = result["audio_clips"]["items"][0]
            self.assertEqual(audio["clip_name"], "Air")
            self.assertEqual(audio["warp_marker_count"], 2)
            self.assertEqual(audio["sample"]["relative_path"], "Samples/air.wav")
            tempo = result["automation"]["tempo_envelopes"][0]
            self.assertEqual(tempo["target"]["manual_value"], 132)
            self.assertTrue(tempo["has_continuous_value_change"])
            self.assertEqual(tempo["events"][1]["attributes"]["Time"], 128)
            self.assertEqual(result["grooves"]["items"][0]["timing_amount"], 66)

    def test_reads_session_midi_advanced_fields(self):
        from ableton_bridge.als_midi import read_als_midi

        with tempfile.TemporaryDirectory() as temp_dir:
            result = read_als_midi(
                self._write_set(Path(temp_dir)), clip_source="session"
            )
            clip = result["clips"][0]
            self.assertEqual(clip["scene_index"], 0)
            self.assertTrue(clip["follow_action"]["enabled"])
            self.assertEqual(clip["groove_id"], 7)
            self.assertEqual(clip["notes"][0]["probability"], 0.75)
            self.assertEqual(clip["notes"][0]["velocity_deviation"], 4)
            self.assertEqual(len(clip["probability_groups"]), 1)
            self.assertEqual(len(clip["per_note_event_lists"]), 1)
            self.assertEqual(clip["clip_envelopes"]["items"][0]["target_id"], 20)

    def test_bounds_device_parameters_audio_clips_and_warp_markers(self):
        from ableton_bridge.als_project import read_als_project

        with tempfile.TemporaryDirectory() as temp_dir:
            result = read_als_project(
                self._write_set(Path(temp_dir)),
                include_device_parameters=True,
                max_parameters_per_device=1,
                max_audio_clips=1,
                max_warp_markers_per_clip=1,
            )
            parameters = result["tracks"][0]["devices"][0]["parameters"]
            self.assertTrue(parameters["has_more"])
            self.assertTrue(
                result["audio_clips"]["items"][0]["warp_markers_has_more"]
            )


if __name__ == "__main__":
    unittest.main()
