import copy
import json

from django.http import HttpResponse
from django.utils.encoding import smart_text

from crashstats.crashstats import utils


def test_enhance_frame():
    vcs_mappings = {
        'hg': {
            'hg.m.org': ('http://hg.m.org/'
                         '%(repo)s/annotate/%(revision)s'
                         '/%(file)s#l%(line)s')
        }
    }

    # Test with a file that uses a vcs_mapping.
    # Also test function sanitizing.
    actual = {
        'frame': 0,
        'module': 'bad.dll',
        'function': 'Func(A * a,B b)',
        'file': 'hg:hg.m.org/repo/name:dname/fname:rev',
        'line': 576,
    }
    utils.enhance_frame(actual, vcs_mappings)
    expected = {
        'function': 'Func(A* a, B b)',
        'short_signature': 'Func',
        'line': 576,
        'source_link': ('http://hg.m.org/repo/name/'
                        'annotate/rev/dname/fname#l576'),
        'file': 'dname/fname',
        'frame': 0,
        'signature': 'Func(A* a, B b)',
        'module': 'bad.dll',
    }
    assert actual == expected

    # Now with a file that has VCS info but isn't in vcs_mappings.
    actual = {
        'frame': 0,
        'module': 'bad.dll',
        'function': 'Func',
        'file': 'git:git.m.org/repo/name:dname/fname:rev',
        'line': 576,
    }
    utils.enhance_frame(actual, vcs_mappings)
    expected = {
        'function': 'Func',
        'short_signature': 'Func',
        'line': 576,
        'file': 'fname',
        'frame': 0,
        'signature': 'Func',
        'module': 'bad.dll',
    }
    assert actual == expected

    # Test with no VCS info at all.
    actual = {
        'frame': 0,
        'module': 'bad.dll',
        'function': 'Func',
        'file': '/foo/bar/file.c',
        'line': 576,
    }
    utils.enhance_frame(actual, vcs_mappings)
    expected = {
        'function': 'Func',
        'short_signature': 'Func',
        'line': 576,
        'file': '/foo/bar/file.c',
        'frame': 0,
        'signature': 'Func',
        'module': 'bad.dll',
    }
    assert actual == expected

    # Test with no source info at all.
    actual = {
        'frame': 0,
        'module': 'bad.dll',
        'function': 'Func',
    }
    utils.enhance_frame(actual, vcs_mappings)
    expected = {
        'function': 'Func',
        'short_signature': 'Func',
        'frame': 0,
        'signature': 'Func',
        'module': 'bad.dll',
    }
    assert actual == expected

    # Test with no function info.
    actual = {
        'frame': 0,
        'module': 'bad.dll',
        'module_offset': '0x123',
    }
    utils.enhance_frame(actual, vcs_mappings)
    expected = {
        'short_signature': 'bad.dll@0x123',
        'frame': 0,
        'signature': 'bad.dll@0x123',
        'module': 'bad.dll',
        'module_offset': '0x123',
    }
    assert actual == expected

    # Test with no module info.
    actual = {
        'frame': 0,
        'offset': '0x1234',
    }
    utils.enhance_frame(actual, vcs_mappings)
    expected = {
        'short_signature': '@0x1234',
        'frame': 0,
        'signature': '@0x1234',
        'offset': '0x1234',
    }
    assert actual == expected


def test_enhance_frame_s3_generated_sources():
    """Test a specific case when the frame references a S3 vcs
    and the file contains a really long sha string"""
    original_frame = {
        'file': (
            's3:gecko-generated-sources:36d62ce2ec2925f4a13e44fe534b246c23b'
            '4b3d5407884d3bbfc9b0d9aebe4929985935ae582704c06e994ece0d1e7652'
            '8ff1edf4543e400d0aaa8f7251b15ca/ipc/ipdl/PCompositorBridgeChild.cpp:'
        ),
        'frame': 22,
        'function': (
            'mozilla::layers::PCompositorBridgeChild::OnMessageReceived(IP'
            'C::Message const&)'
        ),
        'function_offset': '0xd9d',
        'line': 1495,
        'module': 'XUL',
        'module_offset': '0x7c50bd',
        'normalized': 'mozilla::layers::PCompositorBridgeChild::OnMessageReceived',
        'offset': '0x108b7b0bd',
        'short_signature': 'mozilla::layers::PCompositorBridgeChild::OnMessageReceived',
        'signature': (
            'mozilla::layers::PCompositorBridgeChild::OnMessageReceived(IP'
            'C::Message const&)'
        ),
        'trust': 'cfi'
    }
    # Remember, enhance_frame() mutates the dict.
    frame = copy.copy(original_frame)
    utils.enhance_frame(frame, {})
    # Because it can't find a mapping in 'vcs_mappings', the frame's
    # 'file', the default behavior is to extract just the file's basename.
    frame['file'] = 'PCompositorBridgeChild.cpp'

    # Try again, now with 's3' in vcs_mappings.
    frame = copy.copy(original_frame)
    utils.enhance_frame(frame, {
        's3': {
            'gecko-generated-sources': (
                'https://example.com/%(file)s#L-%(line)s'
            ),
        },
    })
    # There's a new key in the frame now. This is what's used in the
    # <a href> in the HTML.
    assert frame['source_link']
    expected = (
        'https://example.com/36d62ce2ec2925f4a13e44fe534b246c23b4b3d540788'
        '4d3bbfc9b0d9aebe4929985935ae582704c06e994ece0d1e76528ff1edf4543e4'
        '00d0aaa8f7251b15ca/ipc/ipdl/PCompositorBridgeChild.cpp#L-1495'
    )
    assert frame['source_link'] == expected

    # And that links text is the frame's 'file' but without the 128 char
    # sha.
    assert frame['file'] == 'ipc/ipdl/PCompositorBridgeChild.cpp'


def test_enhance_json_dump():
    vcs_mappings = {
        'hg': {
            'hg.m.org': ('http://hg.m.org/'
                         '%(repo)s/annotate/%(revision)s'
                         '/%(file)s#l%(line)s')
        }
    }

    actual = {'threads':
              [{'frames':
                [
                    {'frame': 0,
                     'module': 'bad.dll',
                     'function': 'Func',
                     'file': 'hg:hg.m.org/repo/name:dname/fname:rev',
                     'line': 576},
                    {'frame': 1,
                     'module': 'another.dll',
                     'function': 'Func2',
                     'file': 'hg:hg.m.org/repo/name:dname/fname:rev',
                     'line': 576}
                ]},
               {'frames':
                [
                    {'frame': 0,
                     'module': 'bad.dll',
                     'function': 'Func',
                     'file': 'hg:hg.m.org/repo/name:dname/fname:rev',
                     'line': 576},
                    {'frame': 1,
                     'module': 'another.dll',
                     'function': 'Func2',
                     'file': 'hg:hg.m.org/repo/name:dname/fname:rev',
                     'line': 576}
                ]}]}
    utils.enhance_json_dump(actual, vcs_mappings)
    expected = {'threads':
                [{'thread': 0,
                  'frames':
                  [{'frame': 0,
                    'function': 'Func',
                    'short_signature': 'Func',
                    'line': 576,
                    'source_link': ('http://hg.m.org/repo/name/'
                                    'annotate/rev/dname/fname#l576'),
                    'file': 'dname/fname',
                    'signature': 'Func',
                    'module': 'bad.dll'},
                   {'frame': 1,
                    'module': 'another.dll',
                    'function': 'Func2',
                    'signature': 'Func2',
                    'short_signature': 'Func2',
                    'source_link': ('http://hg.m.org/repo/name/'
                                    'annotate/rev/dname/fname#l576'),
                    'file': 'dname/fname',
                    'line': 576}]},
                 {'thread': 1,
                  'frames':
                  [{'frame': 0,
                    'function': 'Func',
                    'short_signature': 'Func',
                    'line': 576,
                    'source_link': ('http://hg.m.org/repo/name/'
                                    'annotate/rev/dname/fname#l576'),
                    'file': 'dname/fname',
                    'signature': 'Func',
                    'module': 'bad.dll'},
                   {'frame': 1,
                    'module': 'another.dll',
                    'function': 'Func2',
                    'signature': 'Func2',
                    'short_signature': 'Func2',
                    'source_link': ('http://hg.m.org/repo/name/'
                                    'annotate/rev/dname/fname#l576'),
                    'file': 'dname/fname',
                    'line': 576}]}]}
    assert actual == expected


def test_find_crash_id():
    # A good string, no prefix
    input_str = '1234abcd-ef56-7890-ab12-abcdef130802'
    crash_id = utils.find_crash_id(input_str)
    assert crash_id == input_str

    # A good string, with prefix
    input_str = 'bp-1234abcd-ef56-7890-ab12-abcdef130802'
    crash_id = utils.find_crash_id(input_str)
    assert crash_id == '1234abcd-ef56-7890-ab12-abcdef130802'

    # A good looking string but not a real day
    input_str = '1234abcd-ef56-7890-ab12-abcdef130230'  # Feb 30th 2013
    assert not utils.find_crash_id(input_str)
    input_str = 'bp-1234abcd-ef56-7890-ab12-abcdef130230'
    assert not utils.find_crash_id(input_str)

    # A bad string, one character missing
    input_str = 'bp-1234abcd-ef56-7890-ab12-abcdef12345'
    assert not utils.find_crash_id(input_str)

    # A bad string, one character not allowed
    input_str = 'bp-1234abcd-ef56-7890-ab12-abcdef12345g'
    assert not utils.find_crash_id(input_str)

    # Close but doesn't end with 6 digits
    input_str = 'f48e9617-652a-11dd-a35a-001a4bd43ed6'
    assert not utils.find_crash_id(input_str)

    # A random string that does not match
    input_str = 'somerandomstringthatdoesnotmatch'
    assert not utils.find_crash_id(input_str)


def test_json_view_basic(rf):
    request = rf.get('/')

    def func(request):
        return {'one': 'One'}

    func = utils.json_view(func)
    response = func(request)
    assert isinstance(response, HttpResponse)
    assert json.loads(response.content) == {'one': 'One'}
    assert response.status_code == 200


def test_json_view_indented(rf):
    request = rf.get('/?pretty=print')

    def func(request):
        return {'one': 'One'}

    func = utils.json_view(func)
    response = func(request)
    assert isinstance(response, HttpResponse)
    assert json.dumps({'one': 'One'}, indent=2) == smart_text(response.content)
    assert response.status_code == 200


def test_json_view_already_httpresponse(rf):
    request = rf.get('/')

    def func(request):
        return HttpResponse('something')

    func = utils.json_view(func)
    response = func(request)
    assert isinstance(response, HttpResponse)
    assert smart_text(response.content) == 'something'
    assert response.status_code == 200


def test_json_view_custom_status(rf):
    request = rf.get('/')

    def func(request):
        return {'one': 'One'}, 403

    func = utils.json_view(func)
    response = func(request)
    assert isinstance(response, HttpResponse)
    assert json.loads(response.content) == {'one': 'One'}
    assert response.status_code == 403
