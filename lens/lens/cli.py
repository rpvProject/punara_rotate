"""Punara Lens CLI. Jobs are plain functions; the nightly pipeline is one command.

Subcommand handlers import their modules lazily so an unbuilt module
(seed, connectors, olap, marts, scores, api) never breaks the others.
"""

from __future__ import annotations

import argparse
import sys

ALL_SOURCES = ("shopify", "klaviyo", "interakt", "gorgias", "judgeme")


def _init_db(_args: argparse.Namespace) -> None:
    from .db import init_db

    init_db()
    print("lens.db initialized (tables + event dictionary).")


def _seed(args: argparse.Namespace) -> None:
    from . import seed
    from .db import get_session

    with get_session() as session:
        report = seed.run(session, tenant_slug=args.tenant, months=args.months, seed=args.seed)
    print(report)


def _sync(args: argparse.Namespace) -> None:
    from .connectors.base import SyncRunner
    from .db import get_session

    sources = [args.source] if args.source else list(ALL_SOURCES)
    with get_session() as session:
        for source in sources:
            try:
                print(SyncRunner().run(session, tenant_id=args.tenant_id, source=source))
            except NotImplementedError as exc:  # phase-2 stub connectors
                print(f"{source}: skipped ({exc})")


def _identity(args: argparse.Namespace) -> None:
    from . import identity
    from .db import get_session

    with get_session() as session:
        print(identity.resolve(session, tenant_id=args.tenant_id))


def _scores(args: argparse.Namespace) -> None:
    from .db import get_session
    from .scores.engine import compute_all

    with get_session() as session:
        for run in compute_all(session, tenant_id=args.tenant_id):
            print(f"{run.score}: {run.value:.1f}")


def _ml(args: argparse.Namespace) -> None:
    from .db import get_session
    from .ml.engine import run

    with get_session() as session:
        print(run(session, tenant_id=args.tenant_id))


def _nightly(args: argparse.Namespace) -> None:
    """The whole pipeline, in order (CONTRACTS.md V2.6):
    sync(all sources) -> identity -> link_direct -> export -> marts -> ml -> scores.
    Phase-2 steps still stubbed skip with a notice instead of failing the run."""
    from . import identity, marts, olap, seed
    from .connectors.base import SyncRunner
    from .db import get_session
    from .scores.engine import compute_all

    tid = args.tenant_id
    with get_session() as session:
        for source in ALL_SOURCES:
            try:
                print(SyncRunner().run(session, tenant_id=tid, source=source))
            except NotImplementedError as exc:  # phase-2 stub connectors
                print(f"{source}: skipped ({exc})")
        print(identity.resolve(session, tenant_id=tid))
        print(f"nps linked to customers: {seed.link_direct(session, tenant_id=tid)}")
        olap.export_core(session, tenant_id=tid)
        marts.build(tenant_id=tid)
        try:
            from .ml.engine import run as ml_run

            print(ml_run(session, tenant_id=tid))
        except NotImplementedError as exc:  # phase-2 stub ml engine
            print(f"ml: skipped ({exc})")
        for run in compute_all(session, tenant_id=tid):
            print(f"{run.score}: {run.value:.1f}")
    print("nightly pipeline complete.")


def _api(_args: argparse.Namespace) -> None:
    import uvicorn

    from .config import settings

    uvicorn.run("lens.api.app:app", host=settings.api_host, port=settings.api_port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lens", description="Punara Lens v0")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create tables + event dictionary").set_defaults(fn=_init_db)

    p = sub.add_parser("seed", help="generate synthetic tenant data")
    p.add_argument("--tenant", default="meadow", help="tenant slug")
    p.add_argument("--months", type=int, default=24)
    p.add_argument("--seed", type=int, default=42, help="RNG seed (deterministic)")
    p.set_defaults(fn=_seed)

    p = sub.add_parser("sync", help="run connector sync")
    p.add_argument("--tenant-id", type=int, default=1)
    p.add_argument("--source", choices=list(ALL_SOURCES), default=None)
    p.set_defaults(fn=_sync)

    p = sub.add_parser("identity", help="run identity resolution")
    p.add_argument("--tenant-id", type=int, default=1)
    p.set_defaults(fn=_identity)

    p = sub.add_parser("scores", help="compute the Punara scores")
    p.add_argument("--tenant-id", type=int, default=1)
    p.set_defaults(fn=_scores)

    p = sub.add_parser("ml", help="batch ML: BG/NBD + Gamma-Gamma + churn bands -> predictions")
    p.add_argument("--tenant-id", type=int, default=1)
    p.set_defaults(fn=_ml)

    p = sub.add_parser("nightly", help="full pipeline: sync -> identity -> export -> marts -> ml -> scores")
    p.add_argument("--tenant-id", type=int, default=1)
    p.set_defaults(fn=_nightly)

    sub.add_parser("api", help="run the REST API on 127.0.0.1:8010").set_defaults(fn=_api)

    args = parser.parse_args(argv)
    try:
        args.fn(args)
    except (ImportError, NotImplementedError) as exc:
        print(f"'{args.command}' is not available yet: {exc}", file=sys.stderr)
        sys.exit(2)
