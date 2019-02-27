# Architecture of `VersionEdges` design

There are a few known facts that are important about version retrieval

The first is that when retrieving pkgs, the server is allowed to return as many
pkg versions as it wants, but must meet the following requirements. Note that
it must meet these requirements even for yanked versions.

- VersionGte: represents a _low edge_. **Must** return the _exact version_ if
  it exists or the lowest version greater than it, as well as return the
  _highest version_ that is not yanked. If the exact version is yanked, it
  **must** return the next highest non-yanked version as well.
- VersionLt: represents a _high_ edge. **Must** return the version _directly
  below_ the version specified. If yanked, **must** return the non-yanked
  versions as well.

For an ultra simple case, these are the pkgs to solve:

- pkgA(2.3) requries pkgB(^1.0), pkgE(>=1.0, <3.0)
- pkgB(1.2 requires pkgE(>=1.2, <2.0)

However, we only know about pkgA in the beginning. So we ask the server
to give us the pkgs we want. The pkgs that exist on the server are

- pkgB: `[1.0, 1.1, 1.2]`
- pkgE: `[1.0, 1.1, 1.2, ..., 1.9, 2.0, 2.5, 2.9]`

The logic in VersionEdges causes the following request to be made:
- `pkgB(>=1.0, <2.0), pkgE(>=1.0, <3.0)`

The server then returns that the following "edge" pkgs exist. It also returns
their dependencies.

```python
pkgB: [
    "1.0": [pkgE(>=1.0, <1.5)],  # lower bound
    "1.2": [pkgE(>=1.2, <2.0)],  # upper bound
]
pkgE: [
    "1.0": [], # lower bound
    "2.9": [], # upper bound
],
```

We injest the new data into our `VersionEdges` object and observe
that new edges have been declared (pkgB(1.0) has a different upper edge and
pkgB(1.2) has different upper and lower edges). We reply to the server with
only the new edges. This returns new pkgE values which may themselves return
new values, etc, etc.

During this process we have a choice:
- attempt to solve the constraint tree
- continue requesting metadata

Eventually all edges will be retrieved. It is up to each application to
determine when is the right time to attempt to solve the constraint tree.

## Reducing the dependencies to real pkgs
The information we now have is:
- A list of pkgs with dependencies that have `Spec` objects, which allow us to
  filter versions (gotten from reading requirements directly).
- pkgEdgesAvailable: A map of concrete pkg versions which are guaranteed to exist.

Our first task is to "reduce" our dependency's semver requirements to a set of
concrete versions.

```python
# we are flattening pkgs to concrete versions only
pkgsVersionsDeps = {}

for pkg, versionsDep in pkgVersionSpecs.items():
    # versionsDep is a dict[version, dict[pkg, Spec]]

    for version, pkgSpecs in versionsDep:
        # store the _actual_ dependencies that are available
        # to that pkg at that version.
        pkgsVersionsDeps[pkg][version] = {
            dep: spec.filter(pkgEdgesAvailable[dep])
            for dep, spec in pkgSpecs.items()
        }
```

We now have a map like this:

```python
pkgsVersionsDeps = {
    pkgA: {
        # pkgA's version
        "2.3": {
            # pkgA's possible dependencies at version 2.3
            "pkgB": [1.0, 1.2],
            "pkgE": [1.0, 1.2, 1.4, 1.9, 2.9],
        },
    },
    pkgB: {
        "1.0": {
            "pkgE": [1.0, 1.2, 1.4],
        },
        "1.2": {
            "pkgE": [1.2, 1.4, 1.9],
        }
    }
}
```

There are a few things to note:
- Some of the edges will never be used. This is _okay_, as requesting such
  simple information from a server is extremely cheap and it helps us a lot to
  be able to reduce the problem set down to real values!
- We have reduced an extremely complex problem (semver's are complicated!) into
  hopefully some set operations. Yay!


## Solving the dependency tree
We now want to "solve" the dependency tree. The solution should:
- Meet every dependency requirement
- Use each pkg only once _if possible_. Note that for some build systems this
  is a hard error (i.e. python).

We therefore first try to find a solution that only uses one pkg version per
pkg. This can only be accomplished recursively, choosing the largest version
of each. For performance note:
- All lists are reverse-sorted so the max can be found in O(1)
- All objects are persistent/functional data structures so can be cloned/"mutated"
  cheaply in each branch.

We will use dynamic programming and backtracking strategies to solve this
problem, taking the greedy assumption that we can always use the largest
packages and only one pkg, and backtracking when that is not the case.

We continuously clone and trim pkgsVersionsDeps, removing fields
that didn't work in our branch. This requires a data structure
that can handle such operations without consuming too much memory,
like the [im](https://crates.rs/crates/im) crate in rust.
or [pyrsistent](python https://github.com/tobgu/pyrsistent)

```python

def solve_dependencies(pkgsVersionsDeps, pkgFullKey):
    pkg, version = pkgFullKey

    if version not in pkgsVersionsDeps[pkg]:
        # A previous step removed this
        raise NotSolved()

    # Hmm... I think this has to be a stack of some kind.
    # - If we cannot solve a (dep, version) then we shouldn't
    #   try again (mark it in failed maybe?)
    # - However, if we broke early because we _thought_ it was
    #   solved then we shouldn't bail that fast...
    for dep, versions in pkgsVersionsDeps[pkg][version]:

        # keep attempting to select the highest version
        solvedDep = False
        for version in versions:
            depFullKey = (dep, version)

            # insert a version of dep with the pinned version.
            reducedDepVersions = {
                version: pkgsVersionsDeps[dep][version]
            }

            # note: creates a new pkgsVersionsDeps
            reducedVersionsAvailble = pkgsVersionsDeps.insert(dep, reducedDepVerions)

            try:
                # Recurse to solve dep's dependencies
                pkgsVersionsDeps = solve_dependencies(
                    failed,
                    reducedVersionsAvailable,
                    depFullKey
                )
                solvedDep = True
                break  # solved this dependency, try to solve the others.
            except NotSolved:
                failed.add(depFullKey)
                pass # try again with a lower version

        if not solvedDep:
            raise NotSolved()

    # managed to solve this tree
    return pkgsVersionsDeps


```

I feel like the above is going all wrong and isn't what I set out to do at all.
The basic idea was to just walk the tree and keep reducing hashsets.

I have a set of pkgs with what versions exist (period!)

```
pkgsVersions = {
    "pkgA": [2.3],
    "pkgB": [1.0, 1.2, 1.4],
    "pkgE": [1.0, 1.2, 1.4, 1.9, 2.9],
}
```

I then walk the dependency tree, removing items from these sets as I go.


```
for pkg, pkgVersionsDeps in pkgsVersionsDeps.items():
    for version, deps in pkgVersionsDeps.items():
        for dep, depVersions in deps.items():
            # only keep versions that are acceptible to this dep
            reduced = pkgsVersions[dep].union(depVersions)
            if not reduced:
                raise NotSolved(dep)

            # pkgsVersions keeps getting smaller
            pkgsVersions[dep] = reduced
```

At the end of the day you are left with a `pkgsVersions` object that is
_guaranteed to meet everyone's needs_. You simply select the max version for
each pkg and be on your way :D


# OLD

We retrieve some pkgs and create a flat map which specifies which pkgs have
which requirements.

```python
pkgsReqs = {
    "pkgA(2.3)": [
        "pkgB(>1.0)"
        "pkgE(>=1,0,<3.0)"
    ],
    "pkgB(1.2)": [
        "pkgE(>=1.2, <2.0)"
    ],
    "pkgE(1.0)": [],
    "pkgE(1.1)": [],
    "pkgE(1.2)": [],
    ...
    "pkgE(1.9)": [],
}
```

We then create a hashmap of pkgs with OrderedSets of all the versions available

```python
pkgsAvailable = {
    pkgA: [2.3],
    pkgB: [1.2],
    pkgE: [1.0, 1.1, 1.2, ..., 1.9],
}

def choose_latest(req):
    pkgKey = req.pkgKey()  # i.e. pkgB(>2.0) -> pkgB
    for available in pkgsAvailable[pkgKey].reverse():
        if req.matches(available):
            return available
    return None
```

There is now one more step. We reduce all reqs down to groups by joining them
all together.

```python
def construct_req_muts():
    req_muts = {}  # Map[pkgKey, set[req]]

    for pkgId, reqs in pkgsReqs:
        for req in reqs:
            reqKey = req.key()
            req_mut = req_muts.get(reqKey)
            if req_mut is None:
                req_mut = ReqMut()

            req_mut.extend_constraints(req)

    return req_muts

req_muts = construct_req_muts()
```

ReqMut calls `.finalize()` to become ReqFinal. ReqFinal is an object which
contains a list of only `ReqRange` objects, representing all of the
non-overlapping "groups" that need to be solved for.

ReqRange(min, max)
- the min and max can both be None.
- the min and max can be inclusive or exclusive.
- if min(inclusive)==max(exclusive) it is an exact version.

We have now constructed a map of objects `Map[PkgKey, FinalReq]`.
We just need to feed the pkgsAvailable to it and we will have
PkgChoices objects. We then walk through the `pkgsReqs` to choose
the dependencies of each pkg and write it to `pkgsImport.libsonnet`
