# Tests for solving edges
from .compat import unittest
from pprint import pprint as pp

from semantic_version import base
from semantic_version import edge
from sortedcontainers import SortedDict

def parse_ex(version_req_str):
    """Helper function to parse with partial=False."""
    return base.VersionReq.parse(version_req_str, partial=False)

# Some shorthands for the test setup
V = base.Version
Vp = base.Version.parse
R = base.VersionReq.parse
S = base.Spec.from_str

pA = "pkgA"
pB = "pkgB"
pC = "pkgC"
pD = "pkgD"
pE = "pkgE"
pF = "pkgF"


# Contains the "server" implementation (not the edges)"
pkgsVersionsSpecsSimple = {
    pA: SortedDict({
        V(2, 3, 0): {
            pB: S("^1.0.0"),
            pE: S(">=1.0.0, <3.0.0"),
        },
    }),

    pB: SortedDict({
        V(1, 0, 0): {
            pE: S(">=1.2.0, <2.0.0"),
        },

        V(1, 1, 0): {
            pE: S(">=1.0.0, <2.0.0"),
        },

        V(1, 2, 0): {
            pE: S(">=1.5.0, <2.5.0"),
        }
    }),

    pE: SortedDict({
        V(mj, mn, 0): {}
        for mj in range(1, 4)
        for mn in range(0, 10, 3)
    }),
}

def get_pkg_edge(db, pkg, edge):
    """Get pkg version which matches the edge from ``db``"""
    pkgVersions = db.get(pkg)
    if pkgVersions is None:
        return None

    if isinstance(edge, EdgeLt):
        # go from highest -> lowest looking for match
        for version in reversed(pkgVersions):
            if edge.match(version):
                return version

    elif isinstance(edge, EdgeGt):
        # go from lowest -> highest looking for match
        for version in pkgVersions:
            if edge.match(version):
                return version

    return None



print("\n\npkgsVersionsSpecsSimple:")
pp(pkgsVersionsSpecsSimple)


class EdgesTestCase(unittest.TestCase):
    def test_append_gte(self):
        e = edge.Edges()
        req = parse_ex(">=1.3.4")
        e.append(req)
        assert e.reqs_gte == {req}
        assert e.reqs_lt == set()

    def test_append_lt(self):
        e = edge.Edges()
        req = parse_ex("<1.3.4")
        e.append(req)
        assert e.reqs_gte == set()
        assert e.reqs_lt == {req}

    def test_append_eq(self):
        e = edge.Edges()
        e.append(parse_ex("==1.2.3"))
        assert e.reqs_gte == {parse_ex(">=1.2.3")}
        assert e.reqs_lt == set()

    def test_append_eq(self):
        e = edge.Edges()
        e.append(parse_ex("!=1.2.3"))
        assert e.reqs_gte == {parse_ex(">=1.2.4")}
        assert e.reqs_lt == {parse_ex("<1.2.3")}

    def test_append_shorteq(self):
        e = edge.Edges()
        e.append(parse_ex("=1.2.3"))
        assert e.reqs_gte == {parse_ex(">=1.2.3")}
        assert e.reqs_lt == set()

    def test_append_any(self):
        e = edge.Edges()
        e.append(parse_ex("*"))
        assert e.reqs_gte == {parse_ex(">=0.0.1")}
        assert e.reqs_lt == set()

    def test_append_lte(self):
        e = edge.Edges()
        e.append(parse_ex("<=2.3.0"))
        assert e.reqs_gte == set()
        assert e.reqs_lt == {parse_ex("<2.3.1")}

    def test_append_gt(self):
        e = edge.Edges()
        e.append(parse_ex(">2.3.99"))
        assert e.reqs_gte == {parse_ex(">=2.3.100")}
        assert e.reqs_lt == set()

    def test_initiailze_simple(self):
        pkgsSpecs = {
            pA: pkgsVersionsSpecsSimple[pA],
        }
        edges = edge.initialize_edges(pkgsSpecs)

        assert edges[pA][V(2, 3, 0)][pB].reqs_lt == {R("<2.3.0")}
        assert edges[pA][V(2, 3, 0)][pB].reqs_gt == {R(">=1.0.0")}

