#!/usr/bin/env python3
"""Read video codec/container metadata with ffprobe; never modifies the input."""
import argparse
import json
import subprocess


def summarize(data):
    fields = ('index', 'codec_type', 'codec_name', 'profile', 'level', 'width', 'height',
              'pix_fmt', 'bits_per_raw_sample', 'avg_frame_rate', 'r_frame_rate',
              'color_space', 'color_transfer', 'color_primaries', 'sample_rate', 'channels')
    streams = [{key: s[key] for key in fields if key in s} for s in data.get('streams', [])]
    return {'format': {k: data.get('format', {}).get(k) for k in ('format_name', 'duration')},
            'streams': streams,
            'note': 'MOV is a container. These metadata do not prove device hardware decode support.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    args = parser.parse_args()
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', '-i', args.video], check=True, capture_output=True, text=True)
    print(json.dumps(summarize(json.loads(result.stdout)), indent=2))
