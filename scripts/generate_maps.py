#!/usr/bin/env python3
"""
Script to generate all possible map variations from a Google Takeout CSV file.
First runs count_countries.py to process the CSV, then generates all map variations.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> bool:
    """
    Run a command and return True if successful, False otherwise.

    Args:
        cmd: Command and arguments as a list
        description: Description of what the command does

    Returns:
        bool: True if command succeeded, False otherwise
    """
    print(f'\n{description}...')
    print(f'Command: {" ".join(cmd)}')

    try:
        result = subprocess.run(cmd, check=True, capture_output=False)  # noqa: S603
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f'Error: Command failed with exit code {e.returncode}', file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f'Error: Command not found: {cmd[0]}', file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Generate all possible map variations from a Google Takeout CSV file'
    )
    parser.add_argument(
        'csv_file',
        help='Path to the Google Takeout CSV file',
    )
    parser.add_argument(
        '--title',
        default='Visited Countries',
        help='Title for the maps (default: "Visited Countries")',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show verbose output from count_countries.py',
    )

    args = parser.parse_args()

    # Validate input file
    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f'Error: CSV file "{args.csv_file}" not found', file=sys.stderr)
        sys.exit(1)

    # Determine output paths
    csv_basename = csv_path.stem
    build_dir = Path('build')
    build_dir.mkdir(exist_ok=True)

    json_file = build_dir / f'{csv_basename}_countries.json'

    # Step 1: Run count_countries.py
    count_cmd = ['uv', 'run', 'scripts/count_countries.py', str(csv_path)]
    if args.verbose:
        count_cmd.append('--verbose')

    if not run_command(count_cmd, 'Step 1: Processing CSV and counting countries'):
        print('\nFailed to process CSV file. Exiting.', file=sys.stderr)
        sys.exit(1)

    # Verify JSON file was created
    if not json_file.exists():
        print(f'\nError: Expected JSON file not found: {json_file}', file=sys.stderr)
        sys.exit(1)

    print(f'\n✓ Successfully created {json_file}')

    # Step 2: Generate all map variations
    print('\n' + '=' * 70)
    print('Step 2: Generating all map variations')
    print('=' * 70)

    # Define all map variations with their settings and output filenames
    variations: list[dict[str, str | list[str]]] = [
        {
            'name': 'Default (states + country legend)',
            'output': f'{csv_basename}_countries.svg',
            'flags': [],
        },
        {
            'name': 'States with labels',
            'output': f'{csv_basename}_countries_labeled.svg',
            'flags': ['--show-labels'],
        },
        {
            'name': 'Full countries (no states)',
            'output': f'{csv_basename}_countries_full.svg',
            'flags': ['--color-full-country'],
        },
        {
            'name': 'Full countries with labels',
            'output': f'{csv_basename}_countries_full_labeled.svg',
            'flags': ['--color-full-country', '--show-labels'],
        },
    ]

    success_count = 0
    failed_variations = []

    for idx, variation in enumerate(variations, 1):
        print(f'\n[{idx}/{len(variations)}] Generating: {variation["name"]}')

        output_filename = variation['output']
        assert isinstance(output_filename, str)
        output_path = build_dir / output_filename

        flags = variation['flags']
        assert isinstance(flags, list)

        plot_cmd = [
            'uv',
            'run',
            'scripts/plot_countries.py',
            str(json_file),
            '--output',
            str(output_path),
            '--title',
            args.title,
        ]
        plot_cmd.extend(flags)

        if run_command(plot_cmd, f'  Creating {variation["output"]}'):
            print(f'  ✓ Saved to: {output_path}')
            success_count += 1
        else:
            failed_variations.append(variation['name'])

    # Summary
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)
    print(f'\nSuccessfully generated {success_count}/{len(variations)} map variations')

    if success_count > 0:
        print(f'\nAll maps saved to: {build_dir}/')
        print('\nGenerated files:')
        for variation in variations:
            output_filename = variation['output']
            assert isinstance(output_filename, str)
            output_path = build_dir / output_filename
            if output_path.exists():
                size_kb = output_path.stat().st_size / 1024
                print(f'  • {output_filename} ({size_kb:.1f} KB)')

    if failed_variations:
        print('\n⚠️  Failed to generate:')
        for name in failed_variations:
            print(f'  • {name}')
        sys.exit(1)
    else:
        print('\n✓ All map variations generated successfully!')


if __name__ == '__main__':
    main()
