

def solve(pkgsVersionsDeps, root):
    state = State(pkgsVersionsDeps)
    state.attempt_pkg_traversal(root)
    return state.pkgsLocked

class NotSolved(Exception):
    """No solution was found in this branch"""


def State(object):
    def __init__(self, pkgsVersionsDeps):
        self.pkgsVersionsDeps = pkgsVersionsDeps
        self.pkgsLocked = {
            pkg: None for pkg in pkgsVersionDeps.keys()
        }
        self.failedVersions = {
            pkg: set() for pkg in pkgsVersionDeps.keys()
        }

    def attempt_pkg_traversal(self, pkg):
        lockedVersion = self.pkgsLocked[pkg]
        if lockedVersion is not None:
            # this pkg has already been locked, attempt to use that version.
            self.attempt_pkgVersion_traversal(pkg, lockedVersion)
            return  # no error == success

        for pkgVersion in self.pkgsVersionsDeps[pkg].keys():
            if pkgVersion in self.failedVersions[pkg]:
                continue

            assert self.pkgsLocked[pkg] == None
            self.pkgsLocked[pkg] = pkgVersion
            try:
                self.attempt_pkgVersion_traversal(pkg, pkgVersion)
                return  # this pkgVersion combination was successful
            except NotSolved:
                self._handle_not_solved()

        raise NotSolved()

    def attempt_pkgVersion_traversal(self, pkg, pkgVersion):
        depsVersions = pkgVersionsDeps[pkg][pkgVersion]


        for dep, depVersions in depsVersions.items():
            lockedDepVersion = self.pkgsLocked[dep]
            if lockedDepVersion is not None:
                if lockedDepVersion in depVersions:
                    # One of our dependencies was locked, and we can use the
                    # locked version.
                    #
                    # Note: we are _within_ the attempt to lock the dependency
                    # at this version.
                    continue
                else:
                    raise NotSolved()

            lockedHere = []
            for depVersion in depVersions:
                if depVersion in self.failedVersions[dep]:
                    continue

                self.pkgsLocked[dep] = depVersion
                try:
                    attempt_pkg_traversal(dep)
                    lockedHere.append(dep)
                    break
                except NotSolved:
                    self._handle_not_solved(dep, depVersion)
            else:
                # `for...else` The `break` was never hit, the dependency was
                # never solved.
                #
                # The dependency was not solved by us. Make sure we clean up
                # all the dependencies we locked and add them to failed
                #
                # TODO: should I add to the failedVersions all versions we
                # locked?
                #
                # I feel like no, somehow these don't "count" as attempts for
                # that version.
                #
                # I think that is true -- we were not trying to solve _for_
                # these, they were just version combinations we _attempted_.
                # Honestly I was looking for a piece of code that _didn't_
                # set failedVersions, letting us try out combinations... this
                # is it!
                for dep in lockedHere:
                    self.pkgsLocked[dep] = None
                raise NotSolved()


    def _handle_not_solved(self, pkg, pkgVersion):
        self.pkgsLocked[pkg] = None
        self.failedVersions[pkg].add(pkgVersion)

