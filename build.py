#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# Copyright (c) 2018 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import argparse
import os
import os.path
import shutil
import subprocess
import sys
import tempfile

# The import path of the project:
IMPORT_PATH = "github.com/container-mgmt/dedicated-portal"

# The name and version of the project:
PROJECT_NAME = "dedicated-portal"

# The values extracted from the command line:
argv = None


def say(what):
    """
    Writes a message to the standard output, and then flushes it, so that
    the output doesn't appear out of order.
    """
    print(what, flush=True)


def cache(function):
    """
    A decorator that creates a cache for the results of a function, so that
    when the function is called the second time the result will be returned
    from the cache without actually executing it.
    """
    cache = dict()

    def helper(*key):
        if key in cache:
            value = cache[key]
        else:
            value = function(*key)
            cache[key] = value
        return value
    return helper


def go_tool(*args):
    """
    Executes a command with the 'GOPATH' environment variable pointing to the
    project specific path, and with the symbolic link as the working directory.
    The argument should be a list containing the complete command line to
    execute.
    """
    # Make sure that the required directories exist:
    go_path = ensure_go_path()
    project_link = ensure_project_link()

    # Modify the environment so that the Go tool will find the project files
    # using the `GOPATH` environment variable. Note that setting the `PWD`
    # environment is necessary, because the `cwd` is always resolved to a
    # real path by the operating system.
    env = dict(os.environ)
    env["GOPATH"] = go_path
    env["PWD"] = project_link

    # Run the Go tool and wait till it finishes:
    say("Running command '{args}'".format(args=" ".join(args)))
    process = subprocess.Popen(
        args=args,
        env=env,
        cwd=project_link,
    )
    result = process.wait()
    if result != 0:
        raise Exception("Command '{args}' failed with exit code {code}".format(
            args=" ".join(args),
            code=result,
        ))


@cache
def ensure_project_dir():
    say("Calculating project directory")
    return os.path.dirname(os.path.realpath(__file__))


@cache
def ensure_go_path():
    """
    Creates and returns the '.gopath' directory that will be used as the
    'GOPATH' for the project.
    """
    project_dir = ensure_project_dir()
    go_path = os.path.join(project_dir, '.gopath')
    if not os.path.exists(go_path):
        say('Creating Go path `{path}`'.format(path=go_path))
        os.mkdir(go_path)
    return go_path


@cache
def ensure_go_bin():
    """
    Creates and returns the Go 'bin' directory that will be used for the
    project.
    """
    go_path = ensure_go_path()
    go_bin = os.path.join(go_path, "bin")
    if not os.path.exists(go_bin):
        os.mkdir(go_bin)
    return go_bin


@cache
def ensure_go_pkg():
    """
    Creates and returns the Go 'pkg' directory that will be used for the
    project.
    """
    go_path = ensure_go_path()
    go_pkg = os.path.join(go_path, "pkg")
    if not os.path.exists(go_pkg):
        os.mkdir(go_pkg)
    return go_pkg


@cache
def ensure_go_src():
    """
    Creates and returns the Go 'src' directory that will be used for the
    project.
    """
    go_path = ensure_go_path()
    go_src = os.path.join(go_path, "src")
    if not os.path.exists(go_src):
        os.mkdir(go_src)
    return go_src


@cache
def ensure_src_link(import_path, src_path):
    """
    Creates the symbolik link that will be used to make the source for the
    given import path appear in the 'GOPATH' expected by go tools. Returns
    the full path of the link.
    """
    project_dir = ensure_project_dir()
    go_src = ensure_go_src()
    src_link = os.path.join(go_src, import_path)
    link_dir = os.path.dirname(src_link)
    if not os.path.exists(link_dir):
        os.makedirs(link_dir)
    if not os.path.exists(src_link):
        os.symlink(src_path, src_link)
    return src_link


@cache
def ensure_project_link():
    """
    Creates the symbolik link that will be used to make the project appear
    in the 'GOPATH' expected by go tools. Returns the full path of the link.
    """
    project_dir = ensure_project_dir()
    return ensure_src_link(IMPORT_PATH, project_dir)


@cache
def ensure_vendor_dir():
    """
    Creates and populates the 'vendor' directory if it doesn't exist yet.
    Returns the full path of the directory.
    """
    project_link = ensure_project_link()
    vendor_dir = os.path.join(project_link, "vendor")
    if not os.path.exists(vendor_dir):
        go_tool("dep", "ensure", "--vendor-only", "-v")
    return vendor_dir


@cache
def ensure_binaries():
    """
    Builds the binaries corresponding to each subdirectory of the 'cmd'
    directory. Returns a list containing the absolute path names of the
    generated binaries.
    """
    # Make sure that the vendor directory is populated:
    ensure_vendor_dir()

    # Get the names of the subdirectories of the 'cmd' directory:
    project_dir = ensure_project_dir()
    cmd_dir = os.path.join(project_dir, 'cmd')
    cmd_names = []
    for cmd_name in os.listdir(cmd_dir):
        cmd_path = os.path.join(cmd_dir, cmd_name)
        if os.path.isdir(cmd_path):
            cmd_names.append(cmd_name)
    cmd_names.sort()

    # Build the binaries:
    for cmd_name in cmd_names:
        say("Building binary '{name}'".format(name=cmd_name))
        cmd_path = "{path}/cmd/{name}".format(path=IMPORT_PATH, name=cmd_name)
        go_tool("go", "install", cmd_path)

    # Build the result:
    go_bin = ensure_go_bin()
    result = []
    for cmd_name in cmd_names:
        cmd_path = os.path.join(go_bin, cmd_name)
        result.append(cmd_path)
    return result


@cache
def ensure_apps():
    """
    Builds the web applications corresponding to each subdirectory of the 'app'
    directory. Returns a list containing the absolute path names of the output
    directories.
    """
    # Get the names of the subdirectories of the 'app' directory:
    project_dir = ensure_project_dir()
    apps_dir = os.path.join(project_dir, "apps")
    app_names = []
    for app_name in os.listdir(apps_dir):
        app_dir = os.path.join(apps_dir, app_name)
        if os.path.isdir(app_dir):
            app_names.append(app_name)
    app_names.sort()

    # Build the applications:
    build_dirs = []
    for app_name in app_names:
        say("Building application '{name}'".format(name=app_name))
        build_dir = ensure_app(app_name)
        build_dirs.append(build_dir)

    # Return the result:
    return build_dirs


@cache
def ensure_app(app_name):
    """
    Builds the web application corresponding to the given name. Returns the
    path of the 'build' directory that contains the generated artifacts.
    """
    # Locate the application directory:
    project_dir = ensure_project_dir()
    app_dir = os.path.join(project_dir, "apps", app_name)

    # Install the dependencies:
    args = [
        "yarn",
        "install",
    ]
    cmd = " ".join(args)
    say("Running command '{cmd}'".format(cmd=cmd))
    process = subprocess.Popen(args=args, cwd=app_dir)
    result = process.wait()
    if result != 0:
        raise Exception("Command '{cmd}' failed with code {code}".format(
           cmd=cmd,
           code=result,
        ))

    # Build the application:
    args = [
        "yarn",
        "build",
    ]
    cmd = " ".join(args)
    say("Running command '{cmd}'".format(cmd=cmd))
    process = subprocess.Popen(args=args, cwd=app_dir)
    result = process.wait()
    if result != 0:
        raise Exception("Command '{cmd}' failed with code {code}".format(
           cmd=cmd,
           code=result,
        ))

    # Return the build directory:
    build_dir = os.path.join(app_dir, "build")
    return build_dir


@cache
def ensure_images():
    """
    Builds the container images corresponding to each subdirectory of the
    'images' directory. Returns a list containing the tags assigned to the
    images.
    """
    # Get the names of the subdirectories of the 'images' directory:
    project_dir = ensure_project_dir()
    images_dir = os.path.join(project_dir, 'images')
    image_names = []
    for image_name in os.listdir(images_dir):
        image_path = os.path.join(images_dir, image_name)
        if os.path.isdir(image_path):
            image_names.append(image_name)
    image_names.sort()

    # Build the images:
    image_tags = []
    for image_name in image_names:
        say("Building image '%s'" % image_name)
        image_tag = ensure_image(image_name)
        image_tags.append(image_tag)

    # Return the list of tags:
    return image_tags


@cache
def ensure_image(image_name):
    """
    Builds the container image corresponding to the given name. Returns the
    tag assigned to the image.
    """
    # Locate the image directory:
    project_dir = ensure_project_dir()
    image_dir = os.path.join(project_dir, "images", image_name)

    # Calculate the image variables:
    image_vars = dict(
        image_name=image_name,
        image_dir=image_dir,
    )

    # Calculate the image tag:
    image_tag = "{project}/{image}:{version}".format(
        project=PROJECT_NAME,
        image=image_name,
        version=argv.version,
    )

    # The binaries and web applications will most probably be included in the
    # images, so we need to make sure that they are built:
    cmd_files = ensure_binaries()
    app_dirs = ensure_apps()

    # The image will be built in a temporary directory, and we need to
    # make sure that it is removed once done:
    try:
        tmp_root = tempfile.mkdtemp(prefix=image_name + ".")
        tmp_dir = os.path.join(tmp_root, "_")
        say("Created temporary directory '%s' to build image '%s'" % (
            tmp_dir, image_name
        ))

        # Copy files from the original image directory to the temporary
        # directory:
        shutil.copytree(image_dir, tmp_dir)

        # Copy the binaries to the temporary directory, as most probably the
        # image will want to use them:
        for cmd_file in cmd_files:
            cmd_name = os.path.basename(cmd_file)
            dst_file = os.path.join(tmp_dir, cmd_name)
            say("Copy binary '{src}' to '{dst}'".format(
                src=cmd_file,
                dst=dst_file,
            ))
            shutil.copyfile(cmd_file, dst_file)
            shutil.copymode(cmd_file, dst_file)

        # Copy the web applications to the temporary directory, as most
        # probably the image will want to use them:
        for build_dir in app_dirs:
            app_dir = os.path.dirname(build_dir)
            app_name = os.path.basename(app_dir)
            dst_dir = os.path.join(tmp_dir, app_name)
            say("Copy web application '{src}' to '{dst}'".format(
                src=build_dir,
                dst=dst_dir,
            ))
            shutil.copytree(build_dir, dst_dir)

        # Run the build:
        args = [
            "docker",
            "build",
            "--tag=%s" % image_tag,
            ".",
        ]
        say("Running command '%s'" % " ".join(args))
        process = subprocess.Popen(args=args, cwd=tmp_dir)
        result = process.wait()
        if result != 0:
            raise Exception("Command '%s' failed with exit code %d" % (
                " ".join(args), result
            ))
    finally:
        shutil.rmtree(tmp_root)

    # Return the tag:
    return image_tag


@cache
def ensure_image_tar(image_tag, compress=False):
    """
    Saves the image with the given tag to a .tar file. Returns the path
    of the .tar file.
    """
    # Calculate the name of the tar file:
    say("Saving image with tag '%s'" % image_tag)
    project_dir = ensure_project_dir()
    tar_name = image_tag
    tar_name = tar_name.replace("/", "_")  # File system friendly.
    tar_name = tar_name.replace(":", "_")  # SSH friendly.
    tar_name += ".tar"
    tar_path = os.path.join(project_dir, tar_name)

    # Run the command:
    args = [
        "docker",
        "save",
        "--output=%s" % tar_path,
        image_tag,
    ]
    say("Running command '%s'" % " ".join(args))
    process = subprocess.Popen(args)
    result = process.wait()
    if result != 0:
        raise Exception("Command '%s' failed with exit code %d" % (
            " ".join(args), result
        ))

    # Compress the tar files:
    if argv.compress:
        args = [
            "gzip",
            "--force",
            tar_path,
        ]
        say("Running command '%s'" % " ".join(args))
        process = subprocess.Popen(args)
        result = process.wait()
        if result != 0:
            raise Exception("Command '%s' failed with exit code %d" % (
                " ".join(args), result
            ))
        tar_path += ".gz"

    # Return the name of the tar file:
    return tar_path


# Command line subcommands
# ------------------------

def build_binaries():
    """
    Build binaries into .gopath/bin/.
    """
    ensure_binaries()


def build_apps():
    """
    Build each browser apps into apps/*/build/.
    """
    ensure_apps()


def build_images():
    """
    Build docker images, and optionally save them as tarballs.
    """
    # Build the images:
    image_tags = ensure_images()

    # Save the images to tar files:
    if argv.save:
        for image_tag in image_tags:
            ensure_image_tar(image_tag)


def lint():
    """
    Run the 'golint' tool on all the source files.
    """
    go_tool(
        "golint",
        "-min_confidence", "0.9",
        "-set_exit_status",
        "./pkg/...",
        "./cmd/...",
    )


def fmt():
    """
    Format all the source files of the project using the 'gofmt' tool.
    """
    go_tool("gofmt", "-s", "-l", "-w", "./pkg/", "./cmd/")


def run_go():
    """
    Run 'go' with correct environment (tip: use -- to pass flags through).
    """
    go_tool("go", *argv.go_args)


def run_dep():
    """
    Run 'dep' with correct environment (tip: use -- to pass flags through).
    """
    go_tool("dep", *argv.dep_args)


def main():
    # Create the top level command line parser:
    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]),
        description="A simple build tool, just for this project.",
    )
    parser.add_argument(
        "--verbose",
        help="Genenerate verbose output.",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--debug",
        help="Genenerate debug, very verbose, output.",
        default=False,
        action="store_true",
    )
    subparsers = parser.add_subparsers(title="subcommands")

    # Create the parser for the 'binaries' command:
    binaries_parser = subparsers.add_parser("binaries", help=build_binaries.__doc__)
    binaries_parser.set_defaults(func=build_binaries)

    # Create the parser for the 'apps' command:
    apps_parser = subparsers.add_parser("apps", help=build_apps.__doc__)
    apps_parser.set_defaults(func=build_apps)

    # Create the parser for the 'lint' command:
    lint_parser = subparsers.add_parser("lint", help=lint.__doc__)
    lint_parser.set_defaults(func=lint)

    # Create the parser for the 'fmt' command:
    fmt_parser = subparsers.add_parser("fmt", help=fmt.__doc__)
    fmt_parser.set_defaults(func=fmt)

    # Create the parser for the 'images' command:
    images_parser = subparsers.add_parser("images", help=build_images.__doc__)
    images_parser.add_argument(
        "--save",
        help="Save the images to tar files.",
        default=False,
        action="store_true",
    )
    images_parser.add_argument(
        "--compress",
        help="Compress the tar files.",
        default=False,
        action="store_true",
    )
    images_parser.add_argument(
        "--version",
        help="Version of the project.",
        default="latest",
    )
    images_parser.set_defaults(func=build_images)

    # Tools that will be executed directly inside the Go environment.
    go_parser = subparsers.add_parser("go", help=run_go.__doc__)
    go_parser.add_argument(
        "go_args",
        nargs="*",
        help="Arguments for go (tip: use -- to pass flags)",
    )
    go_parser.set_defaults(func=run_go)

    dep_parser = subparsers.add_parser("dep", help=run_dep.__doc__)
    dep_parser.add_argument(
        "dep_args",
        nargs="*",
        help="Arguments for dep (tip: use -- to pass flags)",
    )
    dep_parser.set_defaults(func=run_dep)

    # Run the selected tool:
    code = 0

    global argv
    argv = parser.parse_args()
    if not hasattr(argv, "func"):
        parser.print_usage()
        sys.exit(1)
    argv.func()

    # Bye:
    sys.exit(code)


if __name__ == "__main__":
    main()
