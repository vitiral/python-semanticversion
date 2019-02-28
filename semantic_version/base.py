# -*- coding: utf-8 -*-
# Copyright (c) The python-semanticversion project
# This code is distributed under the two-clause BSD License.

from __future__ import unicode_literals

import functools
import re


from .compat import base_cmp


def _to_int(value):
    try:
        return int(value), True
    except ValueError:
        return value, False


def _has_leading_zero(value):
    return (value
            and value[0] == '0'
            and value.isdigit()
            and value != '0')


def identifier_cmp(a, b):
    """Compare two identifier (for pre-release/build components)."""

    a_cmp, a_is_int = _to_int(a)
    b_cmp, b_is_int = _to_int(b)

    if a_is_int and b_is_int:
        # Numeric identifiers are compared as integers
        return base_cmp(a_cmp, b_cmp)
    elif a_is_int:
        # Numeric identifiers have lower precedence
        return -1
    elif b_is_int:
        return 1
    else:
        # Non-numeric identifiers are compared lexicographically
        return base_cmp(a_cmp, b_cmp)


def identifier_list_cmp(a, b):
    """Compare two identifier list (pre-release/build components).

    The rule is:
        - Identifiers are paired between lists
        - They are compared from left to right
        - If all first identifiers match, the longest list is greater.

    >>> identifier_list_cmp(['1', '2'], ['1', '2'])
    0
    >>> identifier_list_cmp(['1', '2a'], ['1', '2b'])
    -1
    >>> identifier_list_cmp(['1'], ['1', '2'])
    -1
    """
    identifier_pairs = zip(a, b)
    for id_a, id_b in identifier_pairs:
        cmp_res = identifier_cmp(id_a, id_b)
        if cmp_res != 0:
            return cmp_res
    # alpha1.3 < alpha1.3.1
    return base_cmp(len(a), len(b))


class Version(object):

    version_re = re.compile(r'^(\d+)\.(\d+)\.(\d+)(?:-([0-9a-zA-Z.-]+))?(?:\+([0-9a-zA-Z.-]+))?$')
    partial_version_re = re.compile(r'^(\d+)(?:\.(\d+)(?:\.(\d+))?)?(?:-([0-9a-zA-Z.-]*))?(?:\+([0-9a-zA-Z.-]*))?$')

    def __init__(self, major, minor, patch, prerelease=(), build=(), partial=False):
        # Note: if partial is True, prerelease and build may or may not be None.
        # It's pretty confusing, but if partial is False then they must be ()

        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = prerelease
        self.build = build

        self.partial = partial

    @staticmethod
    def _coerce(value, allow_none=False):
        if value is None and allow_none:
            return value
        return int(value)

    def next_major(self):
        if self.prerelease and self.minor == 0 and self.patch == 0:
            return Version(self.major, self.minor, self.patch)
        else:
            return Version(self.major + 1, 0, 0)

    def next_minor(self):
        if self.prerelease and self.patch == 0:
            return Version(self.major, self.minor, self.patch)
        else:
            return Version(self.major, self.minor + 1, 0)

    def next_patch(self):
        if self.prerelease:
            return Version(self.major, self.minor, self.patch)
        else:
            return Version(self.major, self.minor, self.patch + 1)

    @classmethod
    def coerce(cls, version_string, partial=False):
        """Coerce an arbitrary version string into a semver-compatible one.

        The rule is:
        - If not enough components, fill minor/patch with zeroes; unless
          partial=True
        - If more than 3 dot-separated components, extra components are "build"
          data. If some "build" data already appeared, append it to the
          extra components

        Examples:
            >>> Version.coerce('0.1')
            Version.parse(0, 1, 0)
            >>> Version.coerce('0.1.2.3')
            Version.parse(0, 1, 2, (), ('3',))
            >>> Version.coerce('0.1.2.3+4')
            Version.parse(0, 1, 2, (), ('3', '4'))
            >>> Version.coerce('0.1+2-3+4_5')
            Version.parse(0, 1, 0, (), ('2-3', '4-5'))
        """
        base_re = re.compile(r'^\d+(?:\.\d+(?:\.\d+)?)?')

        match = base_re.match(version_string)
        if not match:
            raise ValueError(
                "Version string lacks a numerical component: %r"
                % version_string
            )

        version = version_string[:match.end()]
        if not partial:
            # We need a not-partial version.
            while version.count('.') < 2:
                version += '.0'

        if match.end() == len(version_string):
            return Version.parse(version, partial=partial)

        rest = version_string[match.end():]

        # Cleanup the 'rest'
        rest = re.sub(r'[^a-zA-Z0-9+.-]', '-', rest)

        if rest[0] == '+':
            # A 'build' component
            prerelease = ''
            build = rest[1:]
        elif rest[0] == '.':
            # An extra version component, probably 'build'
            prerelease = ''
            build = rest[1:]
        elif rest[0] == '-':
            rest = rest[1:]
            if '+' in rest:
                prerelease, build = rest.split('+', 1)
            else:
                prerelease, build = rest, ''
        elif '+' in rest:
            prerelease, build = rest.split('+', 1)
        else:
            prerelease, build = rest, ''

        build = build.replace('+', '.')

        if prerelease:
            version = '%s-%s' % (version, prerelease)
        if build:
            version = '%s+%s' % (version, build)

        return cls.parse(version, partial=partial)

    @classmethod
    def parse(cls, version_string, partial=False, coerce=False):
        """Parse a version string into a Version.parse() object.

        Args:
            version_string (str), the version string to parse
            partial (bool), whether to accept incomplete input
            coerce (bool), whether to try to map the passed in string into a
                valid Version.
        """
        if not version_string:
            raise ValueError('Invalid empty version string: %r' % version_string)

        if partial:
            version_re = cls.partial_version_re
        else:
            version_re = cls.version_re

        match = version_re.match(version_string)
        if not match:
            raise ValueError('Invalid version string: %r' % version_string)

        major, minor, patch, prerelease, build = match.groups()

        if _has_leading_zero(major):
            raise ValueError("Invalid leading zero in major: %r" % version_string)
        if _has_leading_zero(minor):
            raise ValueError("Invalid leading zero in minor: %r" % version_string)
        if _has_leading_zero(patch):
            raise ValueError("Invalid leading zero in patch: %r" % version_string)

        major = int(major)
        minor = cls._coerce(minor, partial)
        patch = cls._coerce(patch, partial)

        if prerelease is None:
            if partial and (build is None):
                # No build info, strip here
                return cls(major, minor, patch, None, None, partial=partial)
            else:
                prerelease = ()
        elif prerelease == '':
            prerelease = ()
        else:
            prerelease = tuple(prerelease.split('.'))
            cls._validate_identifiers(prerelease, allow_leading_zeroes=False)

        if build is None:
            if partial:
                build = None
            else:
                build = ()
        elif build == '':
            build = ()
        else:
            build = tuple(build.split('.'))
            cls._validate_identifiers(build, allow_leading_zeroes=True)

        return cls(major, minor, patch, prerelease, build, partial=partial)

    @staticmethod
    def _validate_identifiers(identifiers, allow_leading_zeroes=False):
        for item in identifiers:
            if not item:
                raise ValueError(
                    "Invalid empty identifier %r in %r"
                    % (item, '.'.join(identifiers))
                )

            if item[0] == '0' and item.isdigit() and item != '0' and not allow_leading_zeroes:
                raise ValueError("Invalid leading zero in identifier %r" % item)

    def __iter__(self):
        return iter((self.major, self.minor, self.patch, self.prerelease, self.build))

    def __str__(self):
        version = '%d' % self.major
        if self.minor is not None:
            version = '%s.%d' % (version, self.minor)
        if self.patch is not None:
            version = '%s.%d' % (version, self.patch)

        if self.prerelease or (self.partial and self.prerelease == () and self.build is None):
            version = '%s-%s' % (version, '.'.join(self.prerelease))
        if self.build or (self.partial and self.build == ()):
            version = '%s+%s' % (version, '.'.join(self.build))
        return version

    def __repr__(self):
        return '%s(%r%s)' % (
            self.__class__.__name__,
            str(self),
            ', partial=True' if self.partial else '',
        )

    @staticmethod
    def _comparison_functions(partial=False):
        """Retrieve comparison methods to apply on version components.

        This is a private API.

        Args:
            partial (bool): whether to provide 'partial' or 'strict' matching.

        Returns:
            5-tuple of cmp-like functions.
        """

        def prerelease_cmp(a, b):
            """Compare prerelease components.

            Special rule: a version without prerelease component has higher
            precedence than one with a prerelease component.
            """
            if a and b:
                return identifier_list_cmp(a, b)
            elif a:
                # Versions with prerelease field have lower precedence
                return -1
            elif b:
                return 1
            else:
                return 0

        def build_cmp(a, b):
            """Compare build metadata.

            Special rule: there is no ordering on build metadata.
            """
            if a == b:
                return 0
            else:
                return NotImplemented

        def make_optional(orig_cmp_fun):
            """Convert a cmp-like function to consider 'None == *'."""
            @functools.wraps(orig_cmp_fun)
            def alt_cmp_fun(a, b):
                if a is None or b is None:
                    return 0
                return orig_cmp_fun(a, b)

            return alt_cmp_fun

        if partial:
            return [
                base_cmp,  # Major is still mandatory
                make_optional(base_cmp),
                make_optional(base_cmp),
                make_optional(prerelease_cmp),
                make_optional(build_cmp),
            ]
        else:
            return [
                base_cmp,
                base_cmp,
                base_cmp,
                prerelease_cmp,
                build_cmp,
            ]

    def __compare(self, other):
        comparison_functions = self._comparison_functions(partial=self.partial or other.partial)
        comparisons = zip(comparison_functions, self, other)

        for cmp_fun, self_field, other_field in comparisons:
            cmp_res = cmp_fun(self_field, other_field)
            if cmp_res != 0:
                return cmp_res

        return 0

    def __hash__(self):
        return hash((self.major, self.minor, self.patch, self.prerelease, self.build))

    def __cmp__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.__compare(other)

    def __compare_helper(self, other, condition, notimpl_target):
        """Helper for comparison.

        Allows the caller to provide:
        - The condition
        - The return value if the comparison is meaningless (ie versions with
            build metadata).
        """
        if not isinstance(other, self.__class__):
            return NotImplemented

        cmp_res = self.__cmp__(other)
        if cmp_res is NotImplemented:
            return notimpl_target

        return condition(cmp_res)

    def __eq__(self, other):
        return self.__compare_helper(other, lambda x: x == 0, notimpl_target=False)

    def __ne__(self, other):
        return self.__compare_helper(other, lambda x: x != 0, notimpl_target=True)

    def __lt__(self, other):
        return self.__compare_helper(other, lambda x: x < 0, notimpl_target=False)

    def __le__(self, other):
        return self.__compare_helper(other, lambda x: x <= 0, notimpl_target=False)

    def __gt__(self, other):
        return self.__compare_helper(other, lambda x: x > 0, notimpl_target=False)

    def __ge__(self, other):
        return self.__compare_helper(other, lambda x: x >= 0, notimpl_target=False)


class VersionReq(object):
    """A requirement specification."""

    KIND_ANY = '*'
    KIND_LT = '<'
    KIND_LTE = '<='
    KIND_EQUAL = '=='
    KIND_SHORTEQ = '='
    KIND_EMPTY = ''
    KIND_GTE = '>='
    KIND_GT = '>'
    KIND_NEQ = '!='
    KIND_CARET = '^'
    KIND_TILDE = '~'
    KIND_COMPATIBLE = '~='

    # Map a kind alias to its full version
    KIND_ALIASES = {
        KIND_SHORTEQ: KIND_EQUAL,
        KIND_EMPTY: KIND_EQUAL,
    }

    re_spec = re.compile(r'^(<|<=||=|==|>=|>|!=|\^|~|~=)(\d.*)$')

    def __init__(self, kind, version):
        self.kind = kind
        self.version = version

    @classmethod
    def parse(cls, requirement_string, partial=True):
        if not requirement_string:
            raise ValueError("Invalid empty requirement specification: %r" % requirement_string)

        # Special case: the 'any' version spec.
        if requirement_string == '*':
            # FIXME(rett): an empty string? Why not None?
            return cls(cls.KIND_ANY, '')

        match = cls.re_spec.match(requirement_string)
        if not match:
            raise ValueError("Invalid requirement specification: %r" % requirement_string)

        kind, version = match.groups()
        if kind in cls.KIND_ALIASES:
            kind = cls.KIND_ALIASES[kind]

        version = Version.parse(version, partial=partial)
        if partial and version.build is not None and kind not in (cls.KIND_EQUAL, cls.KIND_NEQ):
            raise ValueError(
                "Invalid requirement version %r: build numbers have no ordering."
                % requirement_string
            )

        return cls(kind, version)

    def match(self, version):
        if self.kind == self.KIND_ANY:
            return True
        elif self.kind == self.KIND_LT:
            return version < self.version
        elif self.kind == self.KIND_LTE:
            return version <= self.version
        elif self.kind == self.KIND_EQUAL:
            return version == self.version
        elif self.kind == self.KIND_GTE:
            return version >= self.version
        elif self.kind == self.KIND_GT:
            return version > self.version
        elif self.kind == self.KIND_NEQ:
            return version != self.version
        elif self.kind == self.KIND_CARET:
            if self.version.major != 0:
                upper = self.version.next_major()
            elif self.version.minor != 0:
                upper = self.version.next_minor()
            else:
                upper = self.version.next_patch()
            return self.version <= version < upper
        elif self.kind == self.KIND_TILDE:
            return self.version <= version < self.version.next_minor()
        elif self.kind == self.KIND_COMPATIBLE:
            if self.version.patch is not None:
                upper = self.version.next_minor()
            else:
                upper = self.version.next_major()
            return self.version <= version < upper
        else:  # pragma: no cover
            raise ValueError('Unexpected match kind: %r' % self.kind)

    def __str__(self):
        return '%s%s' % (self.kind, self.version)

    def __repr__(self):
        return '<VersionReq: %s %r>' % (self.kind, self.version)

    def __eq__(self, other):
        if not isinstance(other, VersionReq):
            return NotImplemented
        return self.kind == other.kind and self.version == other.version

    def __hash__(self):
        return hash((self.kind, self.version))


class Spec(object):
    def __init__(self, requirements):
        if not isinstance(requirements, tuple):
            requirements = tuple(requirements)
        self.requirements = requirements

    @classmethod
    def from_str(cls, *strs):
        specs = []
        for multi_spc_strs in strs:
            specs.extend(
                VersionReq.parse(spec_str) for spec_str
                in multi_spc_strs.split(',')
            )
        return cls(specs)

    def match(self, version):
        """Check whether a Version satisfies the Spec."""
        return all(spec.match(version) for spec in self.requirements)

    def filter(self, versions):
        """Filter an iterable of versions satisfying the Spec."""
        for version in versions:
            if self.match(version):
                yield version

    def select(self, versions):
        """Select the best compatible version among an iterable of options."""
        options = list(self.filter(versions))
        if options:
            return max(options)
        return None

    def __contains__(self, version):
        if isinstance(version, Version):
            return self.match(version)
        return False

    def __iter__(self):
        return iter(self.requirements)

    def __str__(self):
        return ','.join(str(spec) for spec in self.requirements)

    def __repr__(self):
        return '<Spec: %r>' % (self.requirements,)

    def __eq__(self, other):
        if not isinstance(other, Spec):
            return NotImplemented

        return set(self.requirements) == set(other.requirements)

    def __hash__(self):
        return hash(self.requirements)


def compare(v1, v2):
    return base_cmp(Version.parse(v1), Version.parse(v2))


def match(spec, version):
    return Spec.from_str(spec).match(Version.parse(version))


def validate(version_string):
    """Validates a version string againt the SemVer specification."""
    try:
        Version.parse(version_string)
        return True
    except ValueError:
        return False
