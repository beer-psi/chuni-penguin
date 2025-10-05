from datetime import datetime

from .misc import TOKYO_TZ


def release_to_chunithm_version(date: datetime) -> str:
    if (
        datetime(2015, 7, 16, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2016, 1, 21, tzinfo=TOKYO_TZ)
    ):
        return "CHUNITHM"
    if (
        datetime(2016, 2, 4, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2016, 7, 28, tzinfo=TOKYO_TZ)
    ):
        return "CHUNITHM PLUS"
    if (
        datetime(2016, 8, 25, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2017, 1, 26, tzinfo=TOKYO_TZ)
    ):
        return "AIR"
    if (
        datetime(2017, 2, 9, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2017, 8, 3, tzinfo=TOKYO_TZ)
    ):
        return "AIR PLUS"
    if (
        datetime(2017, 8, 24, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2018, 2, 22, tzinfo=TOKYO_TZ)
    ):
        return "STAR"
    if (
        datetime(2018, 3, 8, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2018, 10, 11, tzinfo=TOKYO_TZ)
    ):
        return "STAR PLUS"
    if (
        datetime(2018, 10, 25, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2019, 3, 20, tzinfo=TOKYO_TZ)
    ):
        return "AMAZON"
    if (
        datetime(2019, 4, 11, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2019, 10, 10, tzinfo=TOKYO_TZ)
    ):
        return "AMAZON PLUS"
    if (
        datetime(2019, 10, 24, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2020, 7, 2, tzinfo=TOKYO_TZ)
    ):
        return "CRYSTAL"
    if (
        datetime(2020, 7, 16, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 1, 7, tzinfo=TOKYO_TZ)
    ):
        return "CRYSTAL PLUS"
    if (
        datetime(2021, 1, 21, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 4, 28, tzinfo=TOKYO_TZ)
    ):
        return "PARADISE"
    if (
        datetime(2021, 5, 13, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2021, 10, 21, tzinfo=TOKYO_TZ)
    ):
        return "PARADISE LOST"
    if (
        datetime(2021, 11, 4, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2022, 4, 1, tzinfo=TOKYO_TZ)
    ):
        return "NEW"
    if (
        datetime(2022, 4, 14, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2022, 9, 29, tzinfo=TOKYO_TZ)
    ):
        return "NEW PLUS"
    if (
        datetime(2022, 10, 13, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2023, 4, 27, tzinfo=TOKYO_TZ)
    ):
        return "SUN"
    if (
        datetime(2023, 5, 11, tzinfo=TOKYO_TZ)
        <= date
        <= datetime(2023, 11, 23, tzinfo=TOKYO_TZ)
    ):
        return "SUN PLUS"
    return "LUMINOUS"
