"""Creates the installed flavor of repo.bzl by combining repo_template.bzl with
the manifest.bzl and the *.BUILD.bazel stubs.  See README.md for details.
"""

import argparse
import json
import os

from python import runfiles


def _read(pathname):
    # Returns the string contents of the given pathname.
    with open(pathname, "r", encoding="utf-8") as f:
        return f.read()


def _demangle_build_file_name(pathname):
    """Given a runpath to a BUILD file in the current Bazel workspace, returns
    where it should live in the user's drake.bzl workspace (in their installed
    copy of a Drake binary release).
    """
    # For example, it respells
    #   external/drake_models/BUILD.bazel
    # into
    #   external-drake_models-BUILD.bazel
    # or
    #   drake__examples.BUILD.bazel
    # into
    #   examples/BUILD.bazel
    if pathname.startswith("external"):
        return pathname.replace("/", "-")
    result = os.path.basename(pathname)
    result = result.replace("__", "/").replace(".BUILD.bazel", "/BUILD.bazel")
    assert result.startswith("drake/")
    result = result[len("drake/"):]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo_template", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--build_file", action="append", dest="build_files")
    args = parser.parse_args()

    # This will be the new value for _BUILD_FILE_CONTENTS.
    build_file_contents = dict([
        (_demangle_build_file_name(pathname), _read(pathname))
        for pathname in args.build_files
    ])

    # This will be the new value for _MANIFEST.
    manifest_contents = _read(args.manifest)

    # This will provide @@MODELS_...@@ substitutions.
    drake_models_metadata = json.loads(_read(runfiles.Create().Rlocation(
        "drake/multibody/parsing/drake_models.json")))

    # The repo.bzl output is based on repo_template.bzl, with a few
    # programmatic alterations.
    repo_bzl = []
    for line in _read(args.repo_template).splitlines():
        # Strip template-specific comment lines.
        if line.startswith("# * #"):
            continue
        # Handle one-off substitutions.
        if "@@MODELS_URLS@@" in line:
            line = line.replace("@@MODELS_URLS@@",
                                '", "'.join(drake_models_metadata["urls"]))
        if "@@MODELS_SHA256@@" in line:
            line = line.replace("@@MODELS_SHA256@@",
                                drake_models_metadata["sha256"])
        if "@@MODELS_STRIP_PREFIX@@" in line:
            line = line.replace("@@MODELS_STRIP_PREFIX@@",
                                drake_models_metadata["strip_prefix"])
        # Replace _BUILD_FILE_CONTENTS = ...
        if line.startswith("_BUILD_FILE_CONTENTS"):
            assert build_file_contents is not None
            repo_bzl.append("_BUILD_FILE_CONTENTS = {")
            for path, body in build_file_contents.items():
                repo_bzl.append(f'  "{path}": r"""')
                repo_bzl.append(body)
                repo_bzl.append('""",')
            repo_bzl.append("}")
            repo_bzl.append("")
            build_file_contents = None
            continue
        # Replace _MANIFEST = ...
        if line.startswith("_MANIFEST"):
            # The repo.bzl has a leading underscore on _MANIFEST to mark it
            # private.  In manifest.bzl, it uses MANIFEST with no underscore
            # because it is public.  We add in the underscore here.
            assert manifest_contents.startswith("MANIFEST")
            repo_bzl.append("_" + manifest_contents)
            manifest_contents = None
            continue
        # Otherwise, retain the line as-is.
        repo_bzl.append(line)

    # Make sure that we matched both lines.
    assert build_file_contents is None, "Failed to match _BUILD_FILE_CONTENTS"
    assert manifest_contents is None, "Failed to match _MANIFEST"

    # Write repo.bzl.
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(repo_bzl))


if __name__ == "__main__":
    main()
