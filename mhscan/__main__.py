"""Point d'entrée : python -m mhscan <commande>."""
import argparse

from . import calibrate, config
from .keys import Aborted


def main() -> None:
    parser = argparse.ArgumentParser(prog="mhscan", description="Scan des monsties de MH Stories 2")
    sub = parser.add_subparsers(dest="command", required=True)

    cal = sub.add_parser("calibrate", help="calibrer la grille ou le plateau de gènes")
    cal.add_argument("target", choices=["grid", "genes"])
    cal.add_argument("--image", help="utiliser une capture existante au lieu du jeu")

    chk = sub.add_parser("check", help="vérifier la détection sur l'écran actuel")
    chk.add_argument("--image", help="utiliser une capture existante au lieu du jeu")

    sub.add_parser("scan", help="parcourir l'écurie et enregistrer les gènes")

    args = parser.parse_args()
    cfg = config.load()

    if args.command == "calibrate":
        (calibrate.calibrate_grid if args.target == "grid" else calibrate.calibrate_genes)(cfg, args.image)
    elif args.command == "check":
        calibrate.report(cfg, calibrate.capture(cfg, args.image))
    elif args.command == "scan":
        from .scanner import Scanner
        try:
            Scanner(cfg).run()
        except Aborted as exc:
            print(exc)


if __name__ == "__main__":
    main()
