"""Coverage pulls -> data/raw/coverage/.  Usage: .venv/bin/python pipeline/fetch_coverage.py [step ...]
Steps: snap dcwp_tob agm_rfs agm_insp cb gaps   (default: all, in that order)."""
import sys

import coverage_sources as S

STEPS = {"snap": S.snap, "dcwp_tob": S.dcwp_tob, "agm_rfs": S.agm_rfs, "agm_insp": S.agm_insp}


def main(argv):
    try:
        import coverage_cb as CB
        STEPS["cb"] = CB.run
    except ImportError:
        pass
    try:
        import coverage_gaps as G
        STEPS["gaps"] = G.run
    except ImportError:
        pass
    for s in argv or list(STEPS):
        print(f"=== {s}", flush=True)
        STEPS[s]()


if __name__ == "__main__":
    main(sys.argv[1:])
