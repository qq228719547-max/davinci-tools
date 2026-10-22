"""Resolve DRT audio organizer. Python 3.8+, standard library only.

Only native audio track Items and UserDefinedName are changed. Unknown layouts
fail closed. The original archive and every media file remain untouched.
"""
import argparse
from collections import Counter, defaultdict
import copy
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import struct
import sys
import traceback
import zipfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape


class LayoutError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise LayoutError(message)


def view(data):
    # Resolve uses tags such as ListMgt::LmVersion, outside standard XML Namespaces.
    cleaned = re.sub(rb'(<[/]?)([^\s>/]+)',
                     lambda m: m[1] + m[2].replace(b':', b'_'), data)
    return ET.fromstring(cleaned)


def region(data, tag):
    name = re.escape(tag.encode('ascii'))
    m = re.search(rb'<' + name + rb'\s*>(.*?)</' + name + rb'\s*>', data, re.S)
    if m:
        return m.start(1), m.end(1), m[1]
    empty = re.search(rb'<' + name + rb'\s*/>', data)
    if empty:
        return empty.start(), empty.end(), None
    raise LayoutError('Missing native element: ' + tag)


def replace_region(data, tag, content):
    start, end, old = region(data, tag)
    replacement = content if old is not None else (
        b'<' + tag.encode() + b'>' + content + b'</' + tag.encode() + b'>')
    return data[:start] + replacement + data[end:]


def elements(data):
    """Split direct Element children without touching any nested byte strings."""
    spans = []
    depth = 0
    start = 0
    for m in re.finditer(rb'<(/?)Element\s*(/?)>', data):
        closing, empty = bool(m[1]), bool(m[2])
        if closing:
            require(depth > 0, 'Unbalanced Element end tag')
            depth -= 1
            if depth == 0:
                spans.append((start, m.end()))
        elif empty:
            if depth == 0:
                raise LayoutError('Unexpected empty Element')
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    require(depth == 0, 'Unbalanced Element start tag')
    cursor = 0
    for start, end in spans:
        require(not data[cursor:start].strip(), 'Unknown data between native elements')
        cursor = end
    require(not data[cursor:].strip(), 'Unknown trailing native data')
    return [data[a:b] for a, b in spans]


def exact_time(text):
    integer, separator, subframe = (text or '0').partition('|')
    result = Fraction(integer or '0')
    if separator:
        require(len(subframe) == 16, 'Unknown subframe representation')
        number = struct.unpack('<d', bytes.fromhex(subframe))[0]
        require(math.isfinite(number), 'Invalid subframe value')
        result += Fraction.from_float(number)
    return result


def lua_literal(value):
    if value is None:
        return 'nil'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # JSON's Unicode escape is not Lua 5.1 syntax; emit UTF-8 directly.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return '{' + ','.join(lua_literal(x) for x in value) + '}'
    if isinstance(value, dict):
        return '{' + ','.join('[' + lua_literal(k) + ']=' + lua_literal(v)
                              for k, v in value.items()) + '}'
    raise TypeError(type(value))


class Classifier:
    def __init__(self, rules):
        self.rules = rules
        self.categories = {c['id']: c for c in rules['categories']}
        require(len(self.categories) == len(rules['categories']), 'Duplicate category ID')
        require(rules['unknown_category'] in self.categories, 'Unknown fallback category')
        for section in ('overrides', 'folder_rules', 'filename_rules'):
            for rule in rules.get(section, []):
                require(rule['category'] in self.categories, 'Unknown rule category')
                for pattern in rule.get('patterns', []):
                    re.compile(pattern, re.I)

    def classify(self, node):
        name = node.findtext('Name', '')
        path = node.findtext('MediaFilePath', '').replace('\\', '/')
        haystack = path + '\n' + name
        for section, text in (('overrides', haystack),
                              ('folder_rules', path.rsplit('/', 1)[0]),
                              ('filename_rules', name)):
            for rule in self.rules.get(section, []):
                if any(re.search(p, text, re.I) for p in rule.get('patterns', [])):
                    return rule['category'], section
        if PureWindowsPath(path or name).suffix.lower() in self.rules['original_extensions']:
            return 'original', 'camera source'
        return self.rules['unknown_category'], 'unclassified'


def native_items(track):
    _, _, body = region(track, 'Items')
    return elements(body or b'')


def split_components(track, classifier, old_index):
    raw_items = native_items(track)
    nodes = []
    for raw in raw_items:
        wrapper = view(raw)
        require(len(wrapper) == 1, 'Unexpected timeline item wrapper')
        node = wrapper[0]
        require(node.tag in ('Sm2TiAudioClip', 'Sm2TiTransition'),
                'Unsupported audio item: ' + node.tag)
        nodes.append(node)
    parents = list(range(len(nodes)))

    def find(i):
        while parents[i] != i:
            i = parents[i]
        return i

    for j, node in enumerate(nodes):
        if node.tag != 'Sm2TiTransition':
            continue
        position = node.findtext('Position')
        require(position in ('1', '2', '3'), 'Unsupported transition alignment')
        adjacent = [j + 1] if position == '1' else [j - 1] if position == '3' else [j - 1, j + 1]
        for k in adjacent:
            require(0 <= k < len(nodes) and nodes[k].tag == 'Sm2TiAudioClip',
                    'Transition has no adjacent audio clip')
            parents[find(j)] = find(k)
    grouped = defaultdict(list)
    for j in range(len(nodes)):
        grouped[find(j)].append(j)
    components = []
    for indices in grouped.values():
        clips = [nodes[j] for j in indices if nodes[j].tag == 'Sm2TiAudioClip']
        classified = [classifier.classify(c) for c in clips]
        categories = {c for c, reason in classified}
        category = next(iter(categories)) if len(categories) == 1 else classifier.rules['unknown_category']
        reason = ', '.join(sorted({reason for _, reason in classified}))
        if len(categories) > 1:
            reason = 'crossfade connects different categories; retained together for review'
        starts = [exact_time(nodes[j].findtext('Start')) for j in indices]
        ends = [exact_time(nodes[j].findtext('Start')) + exact_time(nodes[j].findtext('Duration'))
                for j in indices]
        require(all(b >= a for a, b in zip(starts, ends)), 'Negative clip duration')
        components.append({'category': category, 'reason': reason, 'old_track': old_index,
                           'start': min(starts), 'end': max(ends),
                           'items': [raw_items[j] for j in indices], 'clips': clips})
    return components


def plan_tracks(tracks, classifier):
    grouped = defaultdict(list)
    for i, track in enumerate(tracks, 1):
        wrapper = view(track)
        require(len(wrapper) == 1 and wrapper[0].tag == 'Sm2TiTrack', 'Unknown audio track type')
        node = wrapper[0]
        require(node.findtext('Type') == '1', 'Non-audio track in AudioTrackVec')
        require(node.findtext('Flags', '0') == '0',
                'Audio track A%d has special flags; unlock/unmute it before organizing' % i)
        for tag in ('FusionCompHolderItems', 'LayersVec'):
            child = node.find(tag)
            require(child is None or (len(child) == 0 and not (child.text or '').strip()),
                    'Layered/Fusion audio tracks are not supported')
        for comp in split_components(track, classifier, i):
            grouped[comp['category']].append(comp)
    lanes = []
    for category in classifier.rules['categories']:
        local = []
        for component in sorted(grouped[category['id']], key=lambda x: (x['start'], x['old_track'])):
            lane = next((l for l in local if l['end'] <= component['start']), None)
            if lane is None:
                lane = {'category': category['id'], 'color': category['color'],
                        'name': '%s %02d' % (category['name'], len(local) + 1),
                        'end': Fraction(-1), 'components': []}
                local.append(lane)
            lane['components'].append(component)
            lane['end'] = component['end']
        lanes += local
    return lanes


def digest(data):
    return hashlib.sha256(data).hexdigest()


def process(input_path, output_path, rules_path, report_prefix):
    input_path, output_path = Path(input_path), Path(output_path)
    require(input_path.resolve() != output_path.resolve(), 'Output must not overwrite the input')
    rules = json.loads(Path(rules_path).read_text(encoding='utf-8-sig'))
    classifier = Classifier(rules)
    with zipfile.ZipFile(input_path) as archive:
        require(sum(info.file_size for info in archive.infolist()) <= rules['max_archive_bytes'],
                'Archive exceeds configured uncompressed size limit')
        require(archive.testzip() is None, 'Corrupt source archive')
        names = archive.namelist()
        require(len(set(names)) == len(names), 'Duplicate DRT archive entries')
        sequences = [n for n in names if n.startswith('SeqContainer/') and n.endswith('.xml')]
        require(len(sequences) == 1, 'Nested/multiple sequence containers need manual handling')
        name = sequences[0]
        raw = archive.read(name)
        start, end, audio_body = region(raw, 'AudioTrackVec')
        tracks = elements(audio_body or b'')
        require(tracks, 'No audio tracks')
        # New native tracks must be created through Resolve's API, never fabricated here.
        subtypes = {view(t)[0].findtext('SubType', '') for t in tracks}
        require(len(subtypes) == 1, 'Mixed audio channel formats are not supported in v1')
        lanes = plan_tracks(tracks, classifier)
        clip_count = sum(len(c['clips']) for l in lanes for c in l['components'])
        require(clip_count > 0, 'No audio clips found')
        result = {'status': 'needs_tracks' if len(lanes) > len(tracks) else 'ready',
                  'required_tracks': len(lanes), 'available_tracks': len(tracks),
                  'clip_count': clip_count,
                  'review_clips': sum(len(c['clips']) for l in lanes if l['category'] == 'review'
                                      for c in l['components']),
                  'output': str(output_path.resolve()).replace('\\', '/'),
                  'report': str(Path(str(report_prefix) + '.csv').resolve()).replace('\\', '/'),
                  'tracks': []}
        rows = []
        new_tracks = []
        expected_items = []
        for index, lane in enumerate(lanes, 1):
            items = [b for c in lane['components'] for b in c['items']]
            expected_items += items
            result['tracks'].append({'name': lane['name'], 'color': lane['color'],
                                     'category': lane['category'],
                                     'clip_count': sum(len(c['clips']) for c in lane['components'])})
            for comp in lane['components']:
                for clip in comp['clips']:
                    rows.append([index, lane['name'], comp['old_track'], clip.findtext('Name'),
                                 clip.findtext('Start'), clip.findtext('Duration'),
                                 clip.findtext('MediaFilePath'), comp['reason']])
            if result['status'] == 'ready':
                template = replace_region(tracks[index - 1], 'Items', b'\r\n' + b'\r\n'.join(items) + b'\r\n')
                replacement = b'<UserDefinedName>' + escape(lane['name']).encode('utf-8') + b'</UserDefinedName>'
                template, changes = re.subn(rb'<UserDefinedName\s*/>|<UserDefinedName>.*?</UserDefinedName>',
                                           lambda _: replacement, template, count=1, flags=re.S)
                require(changes == 1, 'Missing native track name field')
                new_tracks.append(template)
        Path(report_prefix).parent.mkdir(parents=True, exist_ok=True)
        with Path(str(report_prefix) + '.csv').open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(['新轨道', '类别', '原轨道', '素材', '原始开始含子帧', '时长含子帧', '原路径', '分类依据'])
            writer.writerows(rows)
        if result['status'] == 'ready':
            # Leave spare native tracks in place and retain their identities/settings.
            for index, spare in enumerate(tracks[len(lanes):], 1):
                spare = replace_region(spare, 'Items', b'')
                spare = re.sub(rb'<UserDefinedName\s*/>|<UserDefinedName>.*?</UserDefinedName>',
                               lambda _: ('<UserDefinedName>备用 %02d</UserDefinedName>' % index).encode(),
                               spare, count=1, flags=re.S)
                new_tracks.append(spare)
                result['tracks'].append({'name': '备用 %02d' % index, 'color': '',
                                         'category': 'spare', 'clip_count': 0})
            original_items = [b for t in tracks for b in native_items(t)]
            require(Counter(original_items) == Counter(expected_items), 'Native clip/transition integrity mismatch')
            patched = raw[:start] + b'\r\n' + b'\r\n'.join(new_tracks) + b'\r\n' + raw[end:]
            view(patched)
            new_start, new_end, new_audio = region(patched, 'AudioTrackVec')
            require(raw[:start] == patched[:new_start] and raw[end:] == patched[new_end:],
                    'Unexpected video/subtitle/sequence mutation')
            require([view(t)[0].get('DbId') for t in tracks] ==
                    [view(t)[0].get('DbId') for t in new_tracks], 'Track identity changed')
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = output_path.with_suffix(output_path.suffix + '.tmp')
            with zipfile.ZipFile(temporary, 'w') as target:
                for info in archive.infolist():
                    target.writestr(copy.copy(info), patched if info.filename == name else archive.read(info.filename))
            with zipfile.ZipFile(temporary) as target:
                require(target.testzip() is None, 'Output archive integrity failure')
                for entry in names:
                    require(entry == name or target.read(entry) == archive.read(entry),
                            'Media pool or project archive entry changed')
                verify = target.read(name)
                _, _, verify_audio = region(verify, 'AudioTrackVec')
                actual = [b for t in elements(verify_audio) for b in native_items(t)]
                require(Counter(actual) == Counter(original_items), 'Output items changed after packaging')
            temporary.replace(output_path)
            result.update({'input_sha256': digest(input_path.read_bytes()),
                           'output_sha256': digest(output_path.read_bytes()),
                           'native_items_preserved': len(original_items), 'validation': 'passed'})
        Path(str(report_prefix) + '.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--init-run')
    parser.add_argument('--input')
    parser.add_argument('--output')
    parser.add_argument('--rules', default=str(Path(__file__).with_name('rules.json')))
    parser.add_argument('--report')
    parser.add_argument('--result', help='ASCII-path Lua result file consumed by the launcher')
    args = parser.parse_args()
    if args.init_run:
        folder = Path(args.init_run)
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'initialized.txt').write_text('ready', encoding='ascii')
        return 0
    if not all((args.input, args.output, args.report, args.result)):
        parser.error('--input, --output, --report and --result are required')
    try:
        result = process(args.input, args.output, args.rules, args.report)
    except Exception as error:
        result = {'status': 'error', 'message': str(error)}
        Path(str(args.report) + '.error.txt').write_text(traceback.format_exc(), encoding='utf-8')
    Path(args.result).write_text('return ' + lua_literal(result) + '\n', encoding='utf-8')
    if sys.stdout:
        print(json.dumps(result, ensure_ascii=True))
    return 1 if result['status'] == 'error' else 0


if __name__ == '__main__':
    sys.exit(main())
