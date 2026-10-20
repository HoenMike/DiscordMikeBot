"""T30 Dungeon Misfits pure combat engine (experimental; no Discord/database/AI).

Callers MUST persist each RoundResult atomically before displaying it. Re-running
resolve_round with the same state/seed is reproducible, but does not replace
idempotent transactions. No production registration or feature activation here.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, replace
import hashlib
import json
import random
from typing import Mapping

RULES_VERSION = "misfits-0.1-spike"
KINDS = frozenset({"ATTACK", "DEFEND", "ASSIST", "ABILITY", "REPOSITION", "RETREAT"})
ZONES = frozenset({"FRONT", "BACK", "COVER"})
TELEGRAPHS = ("FRONT_SWEEP", "BACK_SPIT", "CHARGE")
SKILLS = {
    "vanguard": ("power_strike", "ward"),
    "skirmisher": ("power_strike", "ward"),
    "arcanist": ("arc_bolt", "disrupt"),
    "support": ("ward", "disrupt"),
    "trickster": ("power_strike", "disrupt"),
}
COSTS = {"power_strike": 1, "arc_bolt": 1, "ward": 1, "disrupt": 2}


class InvalidAction(ValueError):
    """An invalid player action must not alter state."""


@dataclass(frozen=True)
class Stats:
    might: int
    finesse: int
    wits: int
    spirit: int

    def __post_init__(self):
        nums = (self.might, self.finesse, self.wits, self.spirit)
        if any(type(x) is not int or not 0 <= x <= 4 for x in nums) or sum(nums) != 8:
            raise ValueError("Exactly 8 stat points, four integers 0..4")


@dataclass(frozen=True)
class Hero:
    user_id: str
    name: str
    role: str
    stats: Stats
    hp: int
    focus: int = 3
    zone: str = "FRONT"
    shield: int = 0

    @property
    def max_hp(self) -> int:
        return 12 + 2 * self.stats.might

    def __post_init__(self):
        if not self.user_id or not self.name or self.role not in SKILLS:
            raise ValueError("Invalid character identity or role")
        if not 0 <= self.hp <= self.max_hp or not 0 <= self.focus <= 3:
            raise ValueError("Invalid HP or Focus")
        if self.zone not in ZONES or not 0 <= self.shield <= 2:
            raise ValueError("Invalid zone or shield")


def make_hero(uid: str, name: str, role: str, stats: Stats, zone: str = "FRONT") -> Hero:
    return Hero(uid, name, role, stats, hp=12 + 2 * stats.might, zone=zone)


@dataclass(frozen=True)
class Enemy:
    enemy_id: str
    hp: int
    max_hp: int
    defense: int = 12
    armor: int = 1
    damage: int = 3
    telegraph: str = "FRONT_SWEEP"

    def __post_init__(self):
        if not self.enemy_id or self.max_hp <= 0 or not 0 <= self.hp <= self.max_hp:
            raise ValueError("Invalid enemy HP")
        if not 1 <= self.defense <= 20 or not 0 <= self.armor <= 2:
            raise ValueError("Invalid enemy armor/defense")
        if not 0 <= self.damage <= 6 or self.telegraph not in TELEGRAPHS:
            raise ValueError("Invalid enemy attack")


def make_boss(n: int) -> Enemy:
    if not 2 <= n <= 5:
        raise ValueError("Party size 2..5")
    hp = 18 + 6 * (n - 2)
    return Enemy("slime_king", hp, hp)


@dataclass(frozen=True)
class Battle:
    heroes: tuple[Hero, ...]
    enemy: Enemy
    round_no: int = 1
    status: str = "RUNNING"
    rules_version: str = RULES_VERSION

    def __post_init__(self):
        if not 2 <= len(self.heroes) <= 5 or len({x.user_id for x in self.heroes}) != len(self.heroes):
            raise ValueError("Party requires 2..5 distinct users")
        if self.round_no < 1 or self.status not in {"RUNNING", "COMPLETED", "FAILED"}:
            raise ValueError("Invalid battle state")
        if self.rules_version != RULES_VERSION:
            raise ValueError("Unknown rules version")


@dataclass(frozen=True)
class Action:
    kind: str
    target_id: str | None = None
    skill_id: str | None = None
    zone: str | None = None


@dataclass(frozen=True)
class Roll:
    actor: str
    kind: str
    value: int
    modifier: int
    dc: int
    passed: bool


@dataclass(frozen=True)
class Event:
    actor: str
    kind: str
    target: str
    value: int = 0
    detail: str = ""


@dataclass(frozen=True)
class Result:
    round_no: int
    seed: int
    before_hash: str
    after_hash: str
    rolls: tuple[Roll, ...]
    events: tuple[Event, ...]
    state: Battle


def snapshot_hash(state: Battle) -> str:
    data = json.dumps(asdict(state), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


def validate(state: Battle, hero: Hero, action: Action) -> None:
    if action.kind not in KINDS or hero.hp <= 0:
        raise InvalidAction("Unknown action or downed actor")
    if action.kind == "ATTACK":
        if action.target_id != state.enemy.enemy_id or action.skill_id or action.zone:
            raise InvalidAction("ATTACK requires enemy target")
    elif action.kind == "ASSIST":
        allies = {x.user_id for x in state.heroes if x.user_id != hero.user_id and x.hp > 0}
        if action.target_id not in allies or action.skill_id or action.zone:
            raise InvalidAction("ASSIST requires a living ally")
    elif action.kind == "ABILITY":
        if action.skill_id not in SKILLS[hero.role] or hero.focus < COSTS.get(action.skill_id, 99):
            raise InvalidAction("Unavailable skill or insufficient Focus")
        if action.zone:
            raise InvalidAction("Skill cannot include movement")
        if action.skill_id == "ward":
            if action.target_id not in (None, hero.user_id):
                raise InvalidAction("Ward is self-only")
        elif action.target_id != state.enemy.enemy_id:
            raise InvalidAction("Skill requires enemy target")
    elif action.kind == "REPOSITION":
        if action.zone not in ZONES or action.zone == hero.zone or action.target_id or action.skill_id:
            raise InvalidAction("Invalid position change")
    elif action.target_id or action.skill_id or action.zone:
        raise InvalidAction("Unexpected parameters")


def _roll(rng: random.Random, rolls: list[Roll], who: str, kind: str,
          modifier: int, dc: int, attack: bool = False) -> bool:
    value = rng.randint(1, 20)
    passed = (value == 20 or value + modifier >= dc) if attack else value + modifier >= dc
    if attack and value == 1:
        passed = False
    rolls.append(Roll(who, kind, value, modifier, dc, passed))
    return passed


def resolve_round(state: Battle, intents: Mapping[str, Action], *, seed: int) -> Result:
    """One pure turn: validate, guard missing actors, setup assists, execute, enemy."""
    if state.status != "RUNNING" or state.enemy.hp == 0 or not any(h.hp > 0 for h in state.heroes):
        raise ValueError("Cannot resolve finished battle")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Seed must be uint64")
    members = {h.user_id: h for h in state.heroes}
    if set(intents) - set(members):
        raise InvalidAction("Outsider action")
    for uid, action in intents.items():
        if not isinstance(action, Action):
            raise InvalidAction("Expected Action object")
        validate(state, members[uid], action)

    heroes = dict(members)
    enemy = state.enemy
    rng = random.Random(seed)
    rolls: list[Roll] = []
    events: list[Event] = []
    living = [h.user_id for h in state.heroes if h.hp > 0]
    actions = {uid: intents.get(uid, Action("DEFEND")) for uid in living}
    for uid in living:
        if uid not in intents:
            events.append(Event(uid, "AFK_GUARD", uid))
    if all(a.kind == "RETREAT" for a in actions.values()):
        out = replace(state, status="FAILED")
        events.append(Event("party", "RETREAT", enemy.enemy_id))
        return Result(state.round_no, seed, snapshot_hash(state), snapshot_hash(out),
                      (), tuple(events), out)

    # Initiative is rolled/logged even for guards and assists; incoming order does
    # not affect results. Setup actions intentionally precede direct attacks.
    initiatives = {uid: rng.randint(1, 20) + heroes[uid].stats.finesse for uid in living}
    ordered = sorted(living, key=lambda uid: (-initiatives[uid], uid))
    for uid in ordered:
        events.append(Event(uid, "INITIATIVE", uid, initiatives[uid]))
    bonuses: dict[str, int] = {}
    for uid in ordered:
        act = actions[uid]
        if act.kind != "ASSIST":
            continue
        ally_act = actions[act.target_id]
        eligible = ally_act.kind == "ATTACK" or (
            ally_act.kind == "ABILITY" and ally_act.skill_id in {"power_strike", "arc_bolt", "disrupt"})
        if not eligible:
            events.append(Event(uid, "ASSIST_UNUSED", act.target_id))
        elif _roll(rng, rolls, uid, "ASSIST", heroes[uid].stats.wits + 1, 12):
            if bonuses.get(act.target_id, 0) == 0:
                bonuses[act.target_id] = 2
                events.append(Event(uid, "SYNERGY", act.target_id, 2))
            else:
                events.append(Event(uid, "SYNERGY_CAPPED", act.target_id))
        else:
            events.append(Event(uid, "ASSIST_FAILED", act.target_id))

    guarded: set[str] = set()
    interrupted = False
    for uid in ordered:
        act = actions[uid]
        hero = heroes[uid]
        if act.kind == "ASSIST":
            continue
        if act.kind in {"DEFEND", "RETREAT"}:
            guarded.add(uid)
            events.append(Event(uid, "GUARD", uid, 2))
            continue
        if act.kind == "REPOSITION":
            heroes[uid] = replace(hero, zone=act.zone)
            events.append(Event(uid, "REPOSITION", uid, detail=act.zone))
            continue
        if act.kind == "ABILITY":
            hero = replace(hero, focus=hero.focus - COSTS[act.skill_id])
            heroes[uid] = hero
            if act.skill_id == "ward":
                heroes[uid] = replace(hero, shield=2)
                events.append(Event(uid, "SHIELD", uid, 2))
                continue
            if act.skill_id == "disrupt":
                ok = _roll(rng, rolls, uid, "DISRUPT", hero.stats.spirit + 1 + bonuses.get(uid, 0), 12)
                if ok and enemy.telegraph == "CHARGE":
                    interrupted = True
                    events.append(Event(uid, "INTERRUPT", enemy.enemy_id))
                elif ok:
                    events.append(Event(uid, "DISRUPT_PARTIAL", enemy.enemy_id))
                else:
                    events.append(Event(uid, "MISS", enemy.enemy_id))
                continue
        stat = hero.stats.spirit if act.kind == "ABILITY" and act.skill_id == "arc_bolt" else hero.stats.might
        ok = _roll(rng, rolls, uid, "ATTACK", stat + 1 + bonuses.get(uid, 0), enemy.defense, True)
        if ok:
            damage = max(1, 3 + stat // 2 - enemy.armor)
            if act.kind == "ABILITY":
                damage += 2
            if rolls[-1].value == 20:
                damage += 2
            damage = min(damage, enemy.hp)
            enemy = replace(enemy, hp=enemy.hp - damage)
            events.append(Event(uid, "DAMAGE", enemy.enemy_id, damage))
        else:
            events.append(Event(uid, "MISS", enemy.enemy_id))
        if enemy.hp == 0:
            break

    if enemy.hp == 0:
        status = "COMPLETED"
    else:
        zones = {"FRONT_SWEEP": {"FRONT"}, "BACK_SPIT": {"BACK", "COVER"}, "CHARGE": {"FRONT"}}
        targets = [h for h in heroes.values() if h.hp > 0 and h.zone in zones[enemy.telegraph]]
        if enemy.telegraph == "CHARGE" and targets:
            targets = [min(targets, key=lambda h: (h.hp, h.user_id))]
        if interrupted:
            targets = []
        if not targets:
            events.append(Event(enemy.enemy_id, "NO_TARGET", enemy.enemy_id))
        for target in sorted(targets, key=lambda h: h.user_id):
            hero = heroes[target.user_id]
            defense = min(16, 10 + hero.stats.finesse // 2 +
                          (2 if hero.user_id in guarded else 0) + (2 if hero.zone == "COVER" else 0))
            if _roll(rng, rolls, enemy.enemy_id, "ENEMY_ATTACK", 2, defense, True):
                amount = max(0, enemy.damage - hero.shield)
                heroes[hero.user_id] = replace(hero, hp=max(0, hero.hp - amount), shield=0)
                events.append(Event(enemy.enemy_id, "HERO_DAMAGE", hero.user_id, amount))
            else:
                events.append(Event(enemy.enemy_id, "ENEMY_MISS", hero.user_id))
        status = "FAILED" if not any(h.hp > 0 for h in heroes.values()) else "RUNNING"

    updated = replace(state, heroes=tuple(replace(heroes[h.user_id], shield=0) for h in state.heroes),
                      enemy=replace(enemy, telegraph=TELEGRAPHS[state.round_no % len(TELEGRAPHS)]),
                      round_no=state.round_no + (status == "RUNNING"), status=status)
    return Result(state.round_no, seed, snapshot_hash(state), snapshot_hash(updated),
                  tuple(rolls), tuple(events), updated)
