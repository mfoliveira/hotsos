import re
import subprocess

from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.utils import sorted_dict


class DPKGVersionCompare(object):

    def __init__(self, a):
        self.a = a

    def _exec(self, op, b):
        try:
            subprocess.check_call(['dpkg', '--compare-versions',
                                   self.a, op, b])
        except subprocess.CalledProcessError as se:
            if se.returncode == 1:
                return False

            raise se

        return True

    def __eq__(self, b):
        return self._exec('eq', b)

    def __lt__(self, b):
        return not self._exec('ge', b)

    def __gt__(self, b):
        return not self._exec('le', b)

    def __le__(self, b):
        return self._exec('le', b)

    def __ge__(self, b):
        return self._exec('ge', b)


def dict_to_formatted_str_list(f):
    """
    Convert dict returned by function f to a list of strings of format
    '<name> <version>'.
    """
    def _dict_to_formatted_str_list(*args, **kwargs):
        ret = f(*args, **kwargs)
        if not ret:
            return []

        return ["{} {}".format(*e) for e in ret.items()]

    return _dict_to_formatted_str_list


class PackageHelperBase(object):

    def get_version(self, pkg):
        """
        Return version of package.
        """
        raise NotImplementedError

    def is_installed(self, pkg):
        """ Returns True if pkg is installed """
        raise NotImplementedError

    @property
    @dict_to_formatted_str_list
    def all_formatted(self):
        """
        Returns list of packages. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".
        """
        return self.all

    @property
    def all(self):
        """ Returns results matched for all expressions. """
        raise NotImplementedError

    @property
    def core(self):
        """ Returns results matched for core expressions. """
        raise NotImplementedError


class DockerImageHelper(PackageHelperBase):

    def __init__(self, core_pkgs, other_pkgs=None):
        """
        @param core_pkgs:
        package names.
        @param other_pkg_exprs:
        """
        self.core_image_exprs = core_pkgs
        self.other_image_exprs = other_pkgs or []
        self._core_images = {}
        self._other_images = {}
        self._all_images = {}
        # The following expression muct match any package name.
        self._match_expr_template = \
            r"^(\S+/(\S+))\s+([\d\.]+)\s+(\S+)\s+.+"
        self.cli = CLIHelper()

    def _match_image(self, image, entry):
        expr = self._match_expr_template.format(image)
        ret = re.compile(expr).match(entry)
        if ret:
            return ret[1], ret[2], ret[3]

        return None, None, None

    def get_container_images(self):
        images = []
        for line in self.cli.docker_ps():
            ret = re.compile(r"^\S+\s+(\S+):(\S+)\s+.+").match(line)
            if not ret:
                continue

            images.append((ret[1], ret[2]))

        return images

    @property
    def _all(self):
        """ Returns dict of all packages matched. """
        if self._all_images:
            return self._all_images

        used_images = self.get_container_images()
        image_list = self.cli.docker_images()
        if not image_list:
            return

        all_exprs = self.core_image_exprs + self.other_image_exprs
        for line in image_list:
            for image in all_exprs:
                fullname, shortname, version = self._match_image(image, line)
                if shortname is None:
                    continue

                if (fullname, version) not in used_images:
                    continue

                if image in self.core_image_exprs:
                    self._core_images[shortname] = version
                else:
                    self._other_images[shortname] = version

        # ensure sorted
        self._core_images = sorted_dict(self._core_images)
        self._other_images = sorted_dict(self._other_images)
        combined = {}
        combined.update(self._core_images)
        combined.update(self._other_images)
        self._all_images = sorted_dict(combined)

        return self._all_images

    @property
    def all(self):
        """
        Returns list of all images matched.
        """
        return self._all

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of images.
        """
        if self._core_images:
            return self._core_images

        if self._other_images:
            return {}

        # go fetch
        self.all
        return self._core_images


class APTPackageHelper(PackageHelperBase):

    def __init__(self, core_pkgs, other_pkgs=None):
        """
        @param core_pkgs: list of python.re expressions used to match
        package names.
        @param other_pkg_exprs: optional list of python.re expressions used to
        match packages that are not considered part of the core set. This can
        be used to distinguish between core and non-core packages.
        """
        self.core_pkg_exprs = core_pkgs
        self.other_pkg_exprs = other_pkgs or []
        self._core_packages = {}
        self._other_packages = {}
        self._all_packages = {}
        # Match any installed package status
        self._match_expr_template = r"^.i\s+({}[0-9a-z\-]*)\s+(\S+)\s+.+"
        self.cli = CLIHelper()

    def is_installed(self, pkg):
        if pkg in self.all:
            return True

        dpkg_l = self.cli.dpkg_l()
        if not dpkg_l:
            return

        cexpr = re.compile(r"^.i\s+{}\s+.+".format(pkg))
        for line in dpkg_l:
            # See https://man7.org/linux/man-pages/man1/dpkg-query.1.html for
            # package states.
            # Here we check package status not desired action.
            if cexpr.search(line):
                return True

        return False

    def get_version(self, pkg):
        """ Return version of package. """
        if pkg in self._all:
            return self._all[pkg]

        dpkg_l = self.cli.dpkg_l()
        if dpkg_l:
            for line in dpkg_l:
                name, version = self._match_package(pkg, line)
                if name:
                    return version

    def _match_package(self, pkg, entry):
        """ Returns tuple of (package name, version) """
        expr = self._match_expr_template.format(pkg)
        ret = re.compile(expr).match(entry)
        if ret:
            return ret[1], ret[2]

        return None, None

    @property
    def _all(self):
        """ Returns dict of all packages matched. """
        if self._all_packages:
            return self._all_packages

        dpkg_l = self.cli.dpkg_l()
        if not dpkg_l:
            return self._all_packages

        all_exprs = self.core_pkg_exprs + self.other_pkg_exprs
        for line in dpkg_l:
            for pkg in all_exprs:
                name, version = self._match_package(pkg, line)
                if name is None:
                    continue

                if pkg in self.core_pkg_exprs:
                    self._core_packages[name] = version
                else:
                    self._other_packages[name] = version

        # ensure sorted
        self._core_packages = sorted_dict(self._core_packages)
        self._other_packages = sorted_dict(self._other_packages)
        combined = {}
        combined.update(self._core_packages)
        combined.update(self._other_packages)
        self._all_packages = sorted_dict(combined)

        return self._all_packages

    @property
    def all(self):
        """
        Returns list of all packages matched. Each entry in the list is an item
        looking like "<pkgname> <pkgver>".
        """
        return self._all

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of packages.
        """
        if self._core_packages:
            return self._core_packages

        # If _other_packages has contents it implies that we have already
        # collected and there are no core packages so return empty.
        if self._other_packages:
            return self._core_packages

        # go fetch
        self.all
        return self._core_packages


class SnapPackageHelper(PackageHelperBase):

    def __init__(self, core_snaps, other_snaps=None):
        """
        @param core_snaps: list of python.re expressions used to match
        snap names.
        @param other_snap_exprs: optional list of python.re expressions used to
        match snap names for snaps that are not considered part of the
        core set.
        """
        self.core_snap_exprs = core_snaps
        self.other_snap_exprs = other_snaps or []
        self._core_snaps = {}
        self._other_snaps = {}
        self._all_snaps = {}
        self._match_expr_template = \
            r"^ii\s+(python3?-)?({}[0-9a-z\-]*)\s+(\S+)\s+.+"
        self.snap_list_all = CLIHelper().snap_list_all()

    def get_version(self, snap):
        """ Return version of package. """
        if snap in self._all:
            return self._all[snap]

        if self.snap_list_all:
            for line in self.snap_list_all:
                name, version = self._get_snap_info_from_line(line, snap)
                if name:
                    return version

    def _get_snap_info_from_line(self, line, snap):
        """Returns snap name and version if found in line.

        @return: tuple of (name, version) or None, None
        """
        ret = re.compile(r"^({})\s+([\S]+)\s+.+".format(snap)).match(line)
        if ret:
            return (ret[1], ret[2])

        return None, None

    @property
    def _all(self):
        if self._all_snaps:
            return self._all_snaps

        if not self.snap_list_all:
            return {}

        _core = {}
        _other = {}
        all_exprs = self.core_snap_exprs + self.other_snap_exprs
        for line in self.snap_list_all:
            for snap in all_exprs:
                name, version = self._get_snap_info_from_line(line, snap)
                if not name:
                    continue

                # only show latest version installed
                if snap in self.core_snap_exprs:
                    if name in _core:
                        if version > _core[name]:
                            _core[name] = version
                    else:
                        _core[name] = version
                else:
                    if name in _other:
                        if version > _other[name]:
                            _other[name] = version
                    else:
                        _other[name] = version

        # ensure sorted
        self._core_snaps = sorted_dict(_core)
        self._other_snaps = sorted_dict(_other)
        combined = {}
        combined.update(_core)
        combined.update(_other)
        self._all_snaps = sorted_dict(combined)

        return self._all_snaps

    @property
    def all(self):
        """
        Return results that matched from the all/any set of snaps.
        """
        return self._all

    @property
    def core(self):
        """
        Only return results that matched from the "core" set of snaps.
        """
        if self._core_snaps:
            return self._core_snaps

        if self._other_snaps:
            return {}

        # go fetch
        self.all
        return self._core_snaps
