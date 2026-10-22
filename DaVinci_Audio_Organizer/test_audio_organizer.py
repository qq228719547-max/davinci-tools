"""Run with: python -m unittest test_audio_organizer.py"""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
import zipfile
from xml.sax.saxutils import escape

import audio_organizer as tool


def clip(name, path, start=0, duration=20, identity='clip1'):
    return ('<Element><Sm2TiAudioClip DbId="%s"><FieldsBlob>deadbeef</FieldsBlob>'
            '<Name>%s</Name><Start>%s</Start><Duration>%s</Duration>'
            '<MediaRef>native-media-reference</MediaRef><MediaFilePath>%s</MediaFilePath>'
            '<In>123|000000000000d03f</In></Sm2TiAudioClip></Element>' %
            (identity, escape(name), start, duration, escape(path))).encode()


def track(items, identity='track1', subtype='0'):
    return (b'<Element><Sm2TiTrack DbId="' + identity.encode() + b'"><FieldsBlob>1234</FieldsBlob>'
            b'<Type>1</Type><SubType>' + subtype.encode() + b'</SubType><Flags>0</Flags>'
            b'<Sequence>original-sequence</Sequence><Items>' + b''.join(items) +
            b'</Items><FusionCompHolderItems/><UserDefinedName/><LayersVec/></Sm2TiTrack></Element>')


def archive(path, tracks):
    sequence = (b'<?xml version="1.0" encoding="UTF-8"?><Sm2SequenceContainer>'
                b'<VideoTrackVec><Element><ListMgt::NativeData>abcd</ListMgt::NativeData></Element></VideoTrackVec>'
                b'<AudioTrackVec>' + b''.join(tracks) + b'</AudioTrackVec>'
                b'<SubtitleTrackVec>ORIGINAL_SUBTITLES</SubtitleTrackVec></Sm2SequenceContainer>')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('project.xml', b'opaque-project-bytes')
        z.writestr('MediaPool/Master/MpFolder.xml', b'opaque-media-pool-bytes')
        z.writestr('SeqContainer/test.xml', sequence)


class AudioTests(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get('AUDIO_TEST_TMP', str(Path.cwd() / 'test_tmp'))).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self.folder = base / ('test_' + uuid.uuid4().hex)
        self.folder.mkdir()
        if not self.folder.resolve().is_relative_to(base):
            raise ValueError('Test temporary directory escaped the test workspace')
        self.rules = json.loads(Path(__file__).with_name('rules.json').read_text(encoding='utf-8'))
        self.rules_path = self.folder / 'rules.json'
        self.rules_path.write_text(json.dumps(self.rules), encoding='utf-8')
        self.source = self.folder / 'input.drt'
        self.output = self.folder / 'output.drt'

    def process(self):
        return tool.process(self.source, self.output, self.rules_path, self.folder / 'report')

    def test_grouping_preserves_native_bytes_and_media(self):
        music = clip('music.wav', 'F:/素材/音乐/music.wav', identity='music')
        voice = clip('voice.wav', 'F:/素材/配音/voice.wav', identity='voice')
        effect = clip('effect.wav', 'E:/素材/音效/effect.wav', identity='effect')
        archive(self.source, [track([music, voice], 't1'), track([effect], 't2'), track([], 't3')])
        before = self.source.read_bytes()
        result = self.process()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual([t['category'] for t in result['tracks']], ['voice', 'music', 'sfx'])
        self.assertEqual(self.source.read_bytes(), before)
        with zipfile.ZipFile(self.source) as a, zipfile.ZipFile(self.output) as b:
            self.assertEqual(a.read('project.xml'), b.read('project.xml'))
            self.assertEqual(a.read('MediaPool/Master/MpFolder.xml'), b.read('MediaPool/Master/MpFolder.xml'))
            data = b.read('SeqContainer/test.xml')
            for raw in (music, voice, effect):
                self.assertEqual(data.count(raw), 1)
            self.assertIn(b'<ListMgt::NativeData>abcd</ListMgt::NativeData>', data)

    def test_unknown_goes_to_review(self):
        unknown = tool.view(clip('ab12.wav', 'F:/杂项/ab12.wav'))[0]
        self.assertEqual(tool.Classifier(self.rules).classify(unknown)[0], 'review')
        original = tool.view(clip('C1001.MP4', 'F:/拍摄/C1001.MP4'))[0]
        self.assertEqual(tool.Classifier(self.rules).classify(original)[0], 'original')

    def test_overrides_take_priority(self):
        self.rules['overrides'] = [{'category': 'music', 'patterns': ['my_song']}]
        node = tool.view(clip('my_song.wav', 'F:/音效/my_song.wav'))[0]
        self.assertEqual(tool.Classifier(self.rules).classify(node)[0], 'music')

    def test_overlapping_music_requires_native_tracks(self):
        a = clip('a.wav', 'F:/音乐/a.wav', start=0, identity='a')
        b = clip('b.wav', 'F:/音乐/b.wav', start=10, identity='b')
        archive(self.source, [track([a, b])])
        result = self.process()
        self.assertEqual(result['status'], 'needs_tracks')
        self.assertEqual(result['required_tracks'], 2)
        self.assertFalse(self.output.exists())

    def test_crossfade_stays_connected_even_across_categories(self):
        a = clip('a.wav', 'F:/音乐/a.wav', identity='a')
        transition = (b'<Element><Sm2TiTransition DbId="transition"><Start>10</Start>'
                      b'<Duration>10</Duration><Position>2</Position></Sm2TiTransition></Element>')
        b = clip('b.wav', 'F:/音效/b.wav', start=20, identity='b')
        archive(self.source, [track([a, transition, b])])
        result = self.process()
        self.assertEqual(result['review_clips'], 2)
        self.assertEqual(result['tracks'][0]['category'], 'review')
        with zipfile.ZipFile(self.output) as z:
            self.assertIn(a + b'\r\n' + transition + b'\r\n' + b, z.read('SeqContainer/test.xml'))

    def test_subframes_do_not_round_away(self):
        self.assertEqual(tool.exact_time('10|000000000000e03f'), tool.Fraction(21, 2))
        a = clip('a.wav', 'F:/音乐/a.wav', duration='20|000000000000e03f', identity='a')
        b = clip('b.wav', 'F:/音乐/b.wav', start=20, identity='b')
        archive(self.source, [track([a, b])])
        self.assertEqual(self.process()['required_tracks'], 2)

    def test_mixed_formats_fail_without_output(self):
        archive(self.source, [track([clip('a.wav', 'F:/音乐/a.wav')], 'a', '0'), track([], 'b', '1')])
        with self.assertRaisesRegex(tool.LayoutError, 'Mixed audio'):
            self.process()
        self.assertFalse(self.output.exists())

    def test_never_overwrites_source(self):
        with self.assertRaisesRegex(tool.LayoutError, 'overwrite'):
            tool.process(self.source, self.source, self.rules_path, self.folder / 'report')

    def test_unknown_item_fails_closed(self):
        archive(self.source, [track([b'<Element><UnknownAudioThing/></Element>'])])
        with self.assertRaisesRegex(tool.LayoutError, 'Unsupported audio item'):
            self.process()

    def test_spare_tracks_are_cleared_without_losing_items(self):
        first = clip('a.wav', 'F:/音乐/a.wav', identity='a')
        second = clip('b.wav', 'F:/音乐/b.wav', start=30, identity='b')
        archive(self.source, [track([first], 'a'), track([second], 'b')])
        result = self.process()
        self.assertEqual(result['tracks'][1]['category'], 'spare')
        with zipfile.ZipFile(self.output) as z:
            _, _, body = tool.region(z.read('SeqContainer/test.xml'), 'AudioTrackVec')
            tracks = tool.elements(body)
            self.assertEqual(len(tool.native_items(tracks[0])), 2)
            self.assertEqual(tool.native_items(tracks[1]), [])


if __name__ == '__main__':
    unittest.main()
