from collections.abc import Mapping
import os
import re
import subprocess
import tempfile
import venv
import shutil
import csv
from pathlib import Path
import argparse
from pip._vendor import tomli as tomllib  # Make compatible with Python 3.8-3.10


def main():
    args = parse_cli_args()
    packages = extract_packages(args.requirements)
    package_sizes = measure_sizes(packages)
    write_csv(package_sizes, args.output)
    print_results(package_sizes)

index_pattern = r'^(-i|--index-url)\s+.+$'

def parse_cli_args():
    parser = argparse.ArgumentParser(description='Measure after-install package size including dependencies.')
    parser.add_argument('-r', '--requirements',
                        type=str,
                        default='pyproject.toml',
                        help='Path to the pyproject.toml or requirements.txt file. Default: pyproject.toml',
                        )
    parser.add_argument('-o', '--output',
                        type=str,
                        default='package_sizes.csv',
                        help='Path to the output file. Default: package_sizes.csv',
                        )
    args = parser.parse_args()
    return args


def measure_sizes(packages):
    with tempfile.TemporaryDirectory() as tmp_dir:
        package_sizes = []
        for package in packages:
            package_venv = Path(tmp_dir) / ('venv-' + package)
            print(f'Creating new venv {package_venv}')
            venv.create(package_venv, with_pip=True, symlinks=True)

            size_before = get_dir_size(package_venv)
            install_package(package, package_venv)
            size_after = get_dir_size(package_venv)

            size_diff = size_after - size_before
            print(f'Size of {package}: {format_size(size_diff)}\n')

            package_sizes.append((size_diff, package))
            shutil.rmtree(package_venv)
    package_sizes.sort(reverse=True)
    return package_sizes


def install_package(package, venv_dir):
    pip_path = os.path.join(venv_dir, 'bin', 'pip')
    if isinstance(package, Mapping):
        cmd = f'{pip_path} install {package["package"]} -i {package["index"]}'
    else:
        cmd = f'{pip_path} install {package}'
    print(f'Installing {package}:  {cmd}')
    subprocess.run(cmd, shell=True, text=True, capture_output=True, check=True)


def get_dir_size(start_path=Path('.')) -> int:
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def print_results(package_sizes):
    for size, package in package_sizes:
        print(f'{package.rjust(24)}: {format_size(size, padding="-6")}')


def write_csv(package_sizes, output_file):
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Package', 'Total size [MB]', 'Total size [bytes]', 'Visualisation'])
        for size, package in package_sizes:
            hbar = size_hbar(size)
            writer.writerow([package, format_size(size), size, hbar])


def extract_packages(filepath):
    if filepath.endswith('.txt'):
        with open(filepath, 'r') as file:
            return extract_from_requirements_txt(file)
    if filepath.endswith('.toml'):
        with open(filepath, 'rb') as file:
            return extract_from_pyproject_toml(file)
    print('Unknown file type. Supported file types: requirements.txt, pyproject.toml')
    exit(1)


def size_hbar(size, resolution_mb=25):
    hbar = '#' * round(size / 1024 / 1024 / resolution_mb)  # each 25 MB is one #
    return hbar


def format_size(size_in_bytes, padding='', precision=1):
    return f'{size_in_bytes / 1024 / 1024:{padding}.{precision}f} MB'


def extract_from_requirements_txt(file) -> list:
    """
    # This file is autogenerated by pip-compile with Python 3.8
    astroid==3.0.1 \
        --hash=sha256:7d5895c9825e18079c5aeac0572bc2e4c83205c95d416e0b4fee8bc361d2d9ca \
        --hash=sha256:86b0bb7d7da0be1a7c4aedb7974e391b32d4ed89e33de6ed6902b4b15c97577e
        # via pylint

    =>

    ['astroid==3.0.1']
    """
    dependencies = []
    lines = [el.strip() for el in file]
    for i, line in enumerate(file):
        if not line or line.startswith('#') or line.startswith('-'):
            continue
        dependency = line.split()[0]  # 'package==1.0.0 \' -> ['package==1.0.0', '\']
        if re.match(index_pattern, lines[i-1]):
            dependencies.append(dict(package=dependency, index=lines[i-1].replace('-i', '').replace('--index-url', '').strip()))
        else:
            dependencies.append(dependency)
    return dependencies


def extract_from_pyproject_toml(file) -> set:
    pyproject = tomllib.load(file)
    dependencies = \
        pyproject.get("project", {}).get("dependencies", []) + \
        pyproject.get("project", {}).get("dev-dependencies", []) + \
        pyproject.get("project", {}).get("test-dependencies", [])
    poetry_dependencies = \
        list(pyproject.get("tool", {}).get("poetry", {}).get("dependencies", {}).keys()) + \
        list(pyproject.get("tool", {}).get("poetry", {}).get("dev-dependencies", {}).keys()) + \
        list(pyproject.get("tool", {}).get("poetry", {}).get("test-dependencies", {}).keys())
    opt_dependencies = []
    for category in pyproject.get("project", {}).get("optional-dependencies", {}).values():
        opt_dependencies.extend(category)
    all_dependencies = set(dependencies + poetry_dependencies + opt_dependencies) - set('python')
    return all_dependencies


if __name__ == "__main__":
    main()
