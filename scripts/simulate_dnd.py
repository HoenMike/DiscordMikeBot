"""Offline sample: python -m scripts.simulate_dnd (from repository root)."""
from features.dnd.engine import Action, Battle, Stats, make_boss, make_hero, resolve_round


def run():
    party = (
        make_hero("mike", "Mike", "arcanist", Stats(0, 1, 3, 4), "BACK"),
        make_hero("scout", "Scout", "trickster", Stats(2, 3, 3, 0), "COVER"),
        make_hero("tank", "Tank", "vanguard", Stats(4, 1, 2, 1), "FRONT"),
    )
    state = Battle(party, make_boss(len(party)))
    for step in range(1, 11):
        if state.status != "RUNNING":
            break
        acts = {
            "mike": Action("ABILITY", "slime_king", "arc_bolt")
                    if state.heroes[0].focus else Action("ATTACK", "slime_king"),
            "scout": Action("ASSIST", "mike"),
            "tank": Action("ATTACK", "slime_king"),
        }
        result = resolve_round(state, acts, seed=step * 4093)
        state = result.state
        print(f"Round {step}: boss={state.enemy.hp}/{state.enemy.max_hp} status={state.status} hash={result.after_hash[:12]}")
        for event in result.events:
            if event.kind != "INITIATIVE":
                print(f"  {event.actor}: {event.kind} -> {event.target} ({event.value})")
    print("Outcome:", state.status)


if __name__ == "__main__":
    run()
