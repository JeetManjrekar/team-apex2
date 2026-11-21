"""One-command demo reset (W5): archive metrics, restore data/seed, clear uploads and generated exports.
CLI: python -m core.demo reset"""


def reset(keep_metrics: bool = True) -> dict:
    """Restore seed state. Stub: not implemented yet."""
    raise NotImplementedError("W5: implement core/demo.reset")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["reset"]:
        print(reset())
