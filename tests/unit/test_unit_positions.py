from comstar_game_ai.game_io.battle.unit_positions import (
    BattlePositions,
    parse_unit_positions,
    parse_unit_positions_line,
)


SAMPLE = """\
# alliance, army, unit, x, y, rot, width_m, men
0,0,0,123.45,678.90,90.0,20.0,40
1,0,1,200.0,300.5,180.0,15.0,60

blank line above
; comment line
"""


def test_parse_line():
    unit = parse_unit_positions_line("0,0,0,10,20,45,18,32")
    assert unit is not None
    assert unit.alliance_index == 0
    assert unit.men == 32
    assert unit.rotation_deg == 45.0


def test_parse_ignores_comments_and_blanks():
    assert parse_unit_positions_line("# header") is None
    assert parse_unit_positions_line("") is None
    assert parse_unit_positions_line("1,2") is None


def test_parse_full_file():
    positions = parse_unit_positions(SAMPLE)
    assert isinstance(positions, BattlePositions)
    assert len(positions.units) == 2
    assert positions.total_men == 100
    assert len(positions.by_alliance(1)) == 1
