"""Dungeon Misfits T30 engine contracts; no provider, Discord or database."""
from dataclasses import FrozenInstanceError, replace
import unittest

from features.dnd.engine import (
    Action, Battle, Enemy, Hero, InvalidAction, Stats, make_boss, make_hero,
    resolve_round, snapshot_hash, validate,
)


def sample():
    heroes = (
        make_hero("mike", "Mike", "arcanist", Stats(0, 1, 3, 4), "BACK"),
        make_hero("scout", "Scout", "trickster", Stats(2, 3, 3, 0), "COVER"),
        make_hero("tank", "Tank", "vanguard", Stats(4, 1, 2, 1), "FRONT"),
    )
    return Battle(heroes, make_boss(3))


class TestCharacters(unittest.TestCase):
    def test_stats_budget_and_types(self):
        for vals in ((5, 0, 0, 3), (-1, 4, 3, 2), (1, 1, 1, 1),
                     (True, 1, 3, 4), (2.0, 2, 2, 2)):
            with self.subTest(vals=vals), self.assertRaises(ValueError):
                Stats(*vals)

    def test_no_overpowered_character(self):
        s = sample()
        with self.assertRaises(ValueError):
            replace(s.heroes[0], hp=999)
        with self.assertRaises(ValueError):
            replace(s.heroes[0], focus=4)
        with self.assertRaises(ValueError):
            replace(s.heroes[0], role="god")
        with self.assertRaises(ValueError):
            replace(s.heroes[0], shield=999)
        with self.assertRaises(ValueError):
            replace(s, rules_version="unapproved")
        with self.assertRaises(ValueError):
            replace(s, heroes=(s.heroes[0], s.heroes[0]))
        with self.assertRaises(ValueError):
            make_boss(6)

    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            sample().enemy.hp = 500


class TestActions(unittest.TestCase):
    def test_supported_actions(self):
        s = sample()
        hero = s.heroes[0]
        for action in (Action("ATTACK", "slime_king"), Action("DEFEND"),
                       Action("ASSIST", "scout"), Action("ABILITY", "slime_king", "arc_bolt"),
                       Action("REPOSITION", zone="FRONT"), Action("RETREAT")):
            with self.subTest(action=action):
                validate(s, hero, action)

    def test_forbid_action_injection_and_invalid_fields(self):
        s = sample()
        for action in (Action("KILL_EVERYONE"), Action("ATTACK", "other"),
                       Action("ATTACK", "slime_king", "arc_bolt"),
                       Action("ASSIST", "mike"), Action("ASSIST", "unknown"),
                       Action("ABILITY", "slime_king", "infinite_damage"),
                       Action("ABILITY", "slime_king", "ward"),
                       Action("REPOSITION", zone="BACK"),
                       Action("REPOSITION", zone="FRONT", target_id="scout"),
                       Action("DEFEND", skill_id="arc_bolt")):
            with self.subTest(action=action), self.assertRaises(InvalidAction):
                validate(s, s.heroes[0], action)

    def test_no_unfunded_spell_or_downed_action(self):
        s = sample()
        with self.assertRaises(InvalidAction):
            validate(s, replace(s.heroes[0], focus=0), Action("ABILITY", "slime_king", "arc_bolt"))
        with self.assertRaises(InvalidAction):
            validate(s, replace(s.heroes[0], hp=0), Action("DEFEND"))

    def test_outsider_and_untyped_actions(self):
        with self.assertRaises(InvalidAction):
            resolve_round(sample(), {"outsider": Action("DEFEND")}, seed=5)
        with self.assertRaises(InvalidAction):
            resolve_round(sample(), {"mike": {"kind": "ATTACK"}}, seed=5)


class TestCombat(unittest.TestCase):
    def test_replay_and_order_independence(self):
        s = sample()
        actions = {"mike": Action("ABILITY", "slime_king", "arc_bolt"),
                   "scout": Action("ASSIST", "mike"),
                   "tank": Action("ATTACK", "slime_king")}
        first = resolve_round(s, actions, seed=4093)
        second = resolve_round(s, dict(reversed(list(actions.items()))), seed=4093)
        self.assertEqual(first, second)
        self.assertEqual(snapshot_hash(s), first.before_hash)
        self.assertEqual(snapshot_hash(first.state), first.after_hash)
        self.assertNotEqual(first.before_hash, first.after_hash)
        self.assertTrue(all(1 <= x.value <= 20 for x in first.rolls))

    def test_seed_changes_outcome(self):
        a = resolve_round(sample(), {}, seed=10)
        b = resolve_round(sample(), {}, seed=11)
        self.assertNotEqual(a.rolls, b.rolls)

    def test_missing_actor_autoguards(self):
        res = resolve_round(sample(), {}, seed=1)
        self.assertEqual(sum(e.kind == "AFK_GUARD" for e in res.events), 3)
        self.assertEqual([h.focus for h in res.state.heroes], [3, 3, 3])

    def test_synergy_only_for_eligible_attack(self):
        s = sample()
        # Iterate deterministic seeds: assists may fail checks, which is valid.
        successful = [resolve_round(s, {"mike": Action("ATTACK", "slime_king"),
                          "scout": Action("ASSIST", "mike")}, seed=n) for n in range(30)]
        self.assertTrue(any(any(e.kind == "SYNERGY" for e in r.events) for r in successful))
        unused = resolve_round(s, {"mike": Action("DEFEND"), "scout": Action("ASSIST", "mike")}, seed=3)
        self.assertFalse(any(e.kind == "SYNERGY" for e in unused.events))
        self.assertTrue(any(e.kind == "ASSIST_UNUSED" for e in unused.events))

    def test_synergy_cap(self):
        s = sample()
        res = resolve_round(s, {"mike": Action("ATTACK", "slime_king"),
                          "scout": Action("ASSIST", "mike"),
                          "tank": Action("ASSIST", "mike")}, seed=4093)
        self.assertLessEqual(sum(e.value for e in res.events if e.kind == "SYNERGY"), 2)

    def test_focus_and_skill(self):
        res = resolve_round(sample(), {"mike": Action("ABILITY", "slime_king", "arc_bolt")}, seed=5)
        self.assertEqual(res.state.heroes[0].focus, 2)
        ward = resolve_round(sample(), {"tank": Action("ABILITY", "tank", "ward")}, seed=5)
        self.assertEqual(ward.state.heroes[2].focus, 2)
        self.assertTrue(any(e.kind == "SHIELD" for e in ward.events))

    def test_telegraph_and_position(self):
        s = sample()
        res = resolve_round(s, {"scout": Action("REPOSITION", zone="FRONT")}, seed=7)
        self.assertEqual(res.state.heroes[1].zone, "FRONT")
        self.assertEqual(res.state.enemy.telegraph, "BACK_SPIT")

    def test_retreat_requires_party_consensus(self):
        only_one = resolve_round(sample(), {"mike": Action("RETREAT")}, seed=3)
        self.assertEqual(only_one.state.status, "RUNNING")
        everyone = resolve_round(sample(), {x.user_id: Action("RETREAT") for x in sample().heroes}, seed=3)
        self.assertEqual(everyone.state.status, "FAILED")
        with self.assertRaises(ValueError):
            resolve_round(everyone.state, {}, seed=2)

    def test_victory_and_no_enemy_attack_after_kill(self):
        s = sample()
        s = replace(s, enemy=replace(s.enemy, hp=1))
        action = {"mike": Action("ABILITY", "slime_king", "arc_bolt"),
                  "tank": Action("ATTACK", "slime_king")}
        winners = [resolve_round(s, action, seed=n) for n in range(30)]
        winner = next(r for r in winners if r.state.status == "COMPLETED")
        self.assertFalse(any(e.kind == "HERO_DAMAGE" for e in winner.events))
        with self.assertRaises(ValueError):
            resolve_round(winner.state, {}, seed=3)

    def test_failed_party_and_resource_bounds(self):
        s = sample()
        s = replace(s, heroes=tuple(replace(h, hp=1) for h in s.heroes),
                    enemy=replace(s.enemy, damage=6, telegraph="BACK_SPIT"))
        outcomes = [resolve_round(s, {}, seed=n) for n in range(15)]
        self.assertTrue(all(0 <= h.hp <= h.max_hp for r in outcomes for h in r.state.heroes))
        self.assertTrue(all(0 <= h.focus <= 3 for r in outcomes for h in r.state.heroes))

    def test_illegal_seeds(self):
        for seed in (-1, 2**64, True, "5"):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                resolve_round(sample(), {}, seed=seed)


if __name__ == "__main__":
    unittest.main()
