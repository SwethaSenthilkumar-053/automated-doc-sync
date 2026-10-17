from .cli import build_parser, run


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
