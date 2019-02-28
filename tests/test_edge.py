# Tests for solving edges
from .compat import unittest

from semantic_version import base
from semantic_version import edge

def parse_ex(version_req_str):
    """Helper function to parse with partial=False."""
    return base.VersionReq.parse(version_req_str, partial=False)


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



