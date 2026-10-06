"""Point d'entrée : python -m mhscan <commande> [--game mhs1|mhs2|mhs3]."""
import argparse

from . import calibrate, config
from .keys import Aborted


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

    cal = sub.add_parser("calibrate", parents=[common], help="calibrer la grille ou le plateau de gènes")
    cal.add_argument("target", choices=["grid", "genes"])
    cal.add_argument("--image", help="utiliser une capture existante au lieu du jeu")

    chk = sub.add_parser("check", parents=[common], help="vérifier la détection sur l'écran actuel")
    chk.add_argument("--image", help="utiliser une capture existante au lieu du jeu")

    sub.add_parser("scan", parents=[common], help="parcourir l'écurie et enregistrer les gènes")

    args = parser.parse_args()
    game = args.game or choose_game()
    cfg = config.load(game)
    print(f"Jeu : {config.GAMES[game]['name']}")

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
