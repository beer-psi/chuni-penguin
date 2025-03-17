from math import floor

from chunithm_net.models.enums import Rank
from chunithm_net.models.record import Judgements

ONE_ATTACK_IN_JUSTICE = 51
ONE_MISS_IN_JUSTICE = 101
ONE_MISS_IN_ATTACK = 2


def calculate_border(notecount: int) -> dict[Rank, Judgements]:
    tolerance_sssp = notecount // 10
    tolerance_sss = notecount // 4
    tolerance_ssp = notecount // 2
    tolerance_ss = notecount
    tolerance_sp = notecount * 2
    tolerance_s = floor(notecount * 3.5)

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

    border_jcrit_sssp = notecount - border_jus_sssp - border_atk_sssp - border_miss_sssp
    border_jcrit_sss = notecount - border_jus_sss - border_atk_sss - border_miss_sss
    border_jcrit_ssp = notecount - border_jus_ssp - border_atk_ssp - border_miss_ssp
    border_jcrit_ss = notecount - border_jus_ss - border_atk_ss - border_miss_ss
    border_jcrit_sp = notecount - border_jus_sp - border_atk_sp - border_miss_sp
    border_jcrit_s = notecount - border_jus_s - border_atk_s - border_miss_s

    return {
        Rank.SSSp: Judgements(
            border_jcrit_sssp, border_jus_sssp, border_atk_sssp, border_miss_sssp
        ),
        Rank.SSS: Judgements(
            border_jcrit_sss, border_jus_sss, border_atk_sss, border_miss_sss
        ),
        Rank.SSp: Judgements(
            border_jcrit_ssp, border_jus_ssp, border_atk_ssp, border_miss_ssp
        ),
        Rank.SS: Judgements(
            border_jcrit_ss, border_jus_ss, border_atk_ss, border_miss_ss
        ),
        Rank.Sp: Judgements(
            border_jcrit_sp, border_jus_sp, border_atk_sp, border_miss_sp
        ),
        Rank.S: Judgements(border_jcrit_s, border_jus_s, border_atk_s, border_miss_s),
    }


def calculate_score_deduction_per_judgement(notecount: int):
    return {
        "justice": 10_000 * 100 // notecount / 100,
        "attack": 510_000 * 100 // notecount / 100,
        "miss": 1_010_000 * 100 // notecount / 100,
    }
