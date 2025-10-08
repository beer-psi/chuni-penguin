from math import floor

from chuni_penguin.networks.types import Judgements, Rank

ONE_ATTACK_IN_JUSTICE = 51
ONE_MISS_IN_JUSTICE = 101
ONE_MISS_IN_ATTACK = 2


def calculate_border(notecount: int) -> dict[str | Rank, Judgements]:
    # "tolerance" is the number of justices you can have without falling
    # below this score, assuming it's an AJ.
    #
    # this is computed by the fact that a justice is 100/101 units of a
    # justice critical, therefore you can simplify the operation from:
    #    justice_deduction_per_note = (1_010_000 / notecount) * (101 - 100) / 101
    #                               = (1_010_000 / notecount) * 1 / 101
    #                               = (1_010_000 * 1 / 101) / notecount
    #                               = 10_000 / notecount
    #    tolerance_sssp = (1_010_000 - 1_009_000) / justice_deduction_per_note
    #                   = 1_000 / (10_000 / notecount)
    #                   = 1_000 * (notecount / 10_000)
    #                   = notecount / 10
    tolerance_99aj = notecount // 100
    tolerance_sssp = notecount // 10
    tolerance_sss = notecount // 4
    tolerance_ssp = notecount // 2
    tolerance_ss = notecount
    tolerance_sp = notecount * 2
    tolerance_s = floor(notecount * 3.5)

    # the border_miss and border_atk values are just cut out from tolerance at
    # specific ratios, so instead of having a 444-0-0 SSS+ you could have a 87-7-0 SSS+
    # instead, which is somewhat more realistic.
    #
    # for example, on SS+ rank, every 300 justices turn into 1 miss, and every 58
    # justices turn into 1 attack, but you also have to subtract from the stuff already
    # allocated to misses.
    border_miss_sssp = 0
    border_miss_sss = 0
    border_miss_ssp = tolerance_ssp // 300
    border_miss_ss = tolerance_ss // 275
    border_miss_sp = tolerance_sp // 250
    border_miss_s = tolerance_s // 200

    border_atk_sssp = tolerance_sssp // 60 - border_miss_sssp * ONE_MISS_IN_ATTACK
    border_atk_sss = tolerance_sss // 59 - border_miss_sss * ONE_MISS_IN_ATTACK
    border_atk_ssp = tolerance_ssp // 58 - border_miss_ssp * ONE_MISS_IN_ATTACK
    border_atk_ss = tolerance_ss // 56 - border_miss_ss * ONE_MISS_IN_ATTACK
    border_atk_sp = tolerance_sp // 54 - border_miss_sp * ONE_MISS_IN_ATTACK
    border_atk_s = tolerance_s // 53 - border_miss_s * ONE_MISS_IN_ATTACK

    border_jus_99aj = tolerance_99aj
    border_jus_sssp = (
        tolerance_sssp
        - border_atk_sssp * ONE_ATTACK_IN_JUSTICE
        - border_miss_sssp * ONE_MISS_IN_JUSTICE
    )
    border_jus_sss = (
        tolerance_sss
        - border_atk_sss * ONE_ATTACK_IN_JUSTICE
        - border_miss_sss * ONE_MISS_IN_JUSTICE
    )
    border_jus_ssp = (
        tolerance_ssp
        - border_atk_ssp * ONE_ATTACK_IN_JUSTICE
        - border_miss_ssp * ONE_MISS_IN_JUSTICE
    )
    border_jus_ss = (
        tolerance_ss
        - border_atk_ss * ONE_ATTACK_IN_JUSTICE
        - border_miss_ss * ONE_MISS_IN_JUSTICE
    )
    border_jus_sp = (
        tolerance_sp
        - border_atk_sp * ONE_ATTACK_IN_JUSTICE
        - border_miss_sp * ONE_MISS_IN_JUSTICE
    )
    border_jus_s = (
        tolerance_s
        - border_atk_s * ONE_ATTACK_IN_JUSTICE
        - border_miss_s * ONE_MISS_IN_JUSTICE
    )

    border_jcrit_99aj = notecount - border_jus_99aj
    border_jcrit_sssp = notecount - border_jus_sssp - border_atk_sssp - border_miss_sssp
    border_jcrit_sss = notecount - border_jus_sss - border_atk_sss - border_miss_sss
    border_jcrit_ssp = notecount - border_jus_ssp - border_atk_ssp - border_miss_ssp
    border_jcrit_ss = notecount - border_jus_ss - border_atk_ss - border_miss_ss
    border_jcrit_sp = notecount - border_jus_sp - border_atk_sp - border_miss_sp
    border_jcrit_s = notecount - border_jus_s - border_atk_s - border_miss_s

    return {
        "99AJ": Judgements(
            justice_critical=border_jcrit_99aj,
            justice=border_jus_99aj,
            attack=0,
            miss=0,
        ),
        Rank.sssp: Judgements(
            justice_critical=border_jcrit_sssp,
            justice=border_jus_sssp,
            attack=border_atk_sssp,
            miss=border_miss_sssp,
        ),
        Rank.sss: Judgements(
            justice_critical=border_jcrit_sss,
            justice=border_jus_sss,
            attack=border_atk_sss,
            miss=border_miss_sss,
        ),
        Rank.ssp: Judgements(
            justice_critical=border_jcrit_ssp,
            justice=border_jus_ssp,
            attack=border_atk_ssp,
            miss=border_miss_ssp,
        ),
        Rank.ss: Judgements(
            justice_critical=border_jcrit_ss,
            justice=border_jus_ss,
            attack=border_atk_ss,
            miss=border_miss_ss,
        ),
        Rank.sp: Judgements(
            justice_critical=border_jcrit_sp,
            justice=border_jus_sp,
            attack=border_atk_sp,
            miss=border_miss_sp,
        ),
        Rank.s: Judgements(
            justice_critical=border_jcrit_s,
            justice=border_jus_s,
            attack=border_atk_s,
            miss=border_miss_s,
        ),
    }


def calculate_score_deduction_per_judgement(notecount: int):
    return {
        "justice": 10_000 * 100 // notecount / 100,
        "attack": 510_000 * 100 // notecount / 100,
        "miss": 1_010_000 * 100 // notecount / 100,
    }
