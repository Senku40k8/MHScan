"""Point d'entrée : python -m mhscan <commande> [--game mhs1|mhs2|mhs3]."""
import argparse

from . import calibrate, config, keys


def choose_game() -> str:
    """Menu de choix du jeu quand --game n'est pas précisé."""
    games = list(config.GAMES)
    print("Quel jeu ?")
    for i, key in enumerate(games, 1):
        print(f"  {i}. {config.GAMES[key]['name']} ({key})")
    while True:
        answer = input("Choix : ").strip().lower()
        if answer in games:
            return answer
        if answer.isdigit() and 1 <= int(answer) <= len(games):
            return games[int(answer) - 1]
        print(f"Réponse invalide, tape un numéro entre 1 et {len(games)}.")


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--game", choices=list(config.GAMES), help="jeu à scanner (demandé si absent)")

    parser = argparse.ArgumentParser(prog="mhscan", description="Scan des monsties de Monster Hunter Stories 1, 2 et 3")
    sub = parser.add_subparsers(dest="command", required=True)

    cal = sub.add_parser("calibrate", parents=[common], help="calibrer la grille, le plateau de gènes, l'indicateur de page, la légende ou la fiche")
    cal.add_argument("target", choices=["grid", "genes", "page", "legend", "info"])
    cal.add_argument("--image", help="utiliser une capture existante au lieu du jeu")

    chk = sub.add_parser("check", parents=[common], help="vérifier la détection sur l'écran actuel")
    chk.add_argument("--image", help="utiliser une capture existante au lieu du jeu")

    scn = sub.add_parser("scan", parents=[common], help="parcourir l'écurie et enregistrer les gènes")
    scn.add_argument("--assiste", action="store_true",
                     help="mode assisté : tu déplaces le curseur, chaque monstie survolé est enregistré")

    rap = sub.add_parser("rapport", parents=[common], help="ouvrir le rapport visuel du dernier scan")
    rap.add_argument("--scan", help="dossier d'un scan précis (par défaut : la liste de référence, sinon le dernier scan)")

    args = parser.parse_args()
    game = args.game or choose_game()
    if args.command != "rapport":  # dans le rapport, taper « c » (une recherche...) ne doit rien arrêter
        keys.start_quit_watch()
        print(f"À tout moment, {keys.QUIT_HINT}.")
    try:
        run(args, game)
    except keys.Aborted as exc:
        raise SystemExit(str(exc))


def open_report(args, game: str) -> None:
    from pathlib import Path

    from . import collection, report
    game_dir = Path("scans") / game
    if args.scan:
        scan_dir = Path(args.scan)
    else:
        current = collection.load(game_dir)
        scans = sorted(p for p in game_dir.glob("*/monsties.json")) if game_dir.exists() else []
        if current:
            scan_dir = game_dir / current["scan"]
        elif scans:
            scan_dir = scans[-1].parent
        else:
            raise SystemExit(f"Aucun scan trouvé dans {game_dir}.")
    report.build(scan_dir)
    report.serve(scan_dir)


def run(args, game: str) -> None:
    cfg = config.load(game)
    print(f"Jeu : {config.GAMES[game]['name']}")

    if args.command == "calibrate":
        if args.target == "grid":
            calibrate.calibrate_grid(cfg, args.image)
        elif args.target == "genes":
            calibrate.calibrate_genes(cfg, args.image)
        else:
            calibrate.calibrate_region(cfg, args.target, args.image)
    elif args.command == "check":
        calibrate.report(cfg, calibrate.capture(cfg, args.image))
        print(f"\ncheck ne fait que vérifier la détection. Pour scanner l'écurie : python -m mhscan scan --game {game}")
    elif args.command == "scan":
        from .scanner import Scanner
        try:
            scanner = Scanner(cfg)
        except RuntimeError as exc:
            raise SystemExit(f"Scan impossible : {exc}")
        out = scanner.run(assisted=args.assiste)
        if (out / "rapport.html").exists():
            from . import report
            keys.stop_quit_watch()  # le scan est fini : la touche C ne doit plus rien arrêter
            report.serve(out)
    elif args.command == "rapport":
        open_report(args, game)


if __name__ == "__main__":
    main()
