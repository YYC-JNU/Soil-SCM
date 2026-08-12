from src.scenario_controller import ScenarioController


FERT = {"n": 12.0, "p2o5": 4.0, "k2o": 9.0, "mgo": 3.0,
        "znso4": 1.0, "apply_months": [3, 6, 9]}
LIME = {"amount_per_apply": 45.0, "apply_months": [3, 6, 9]}


def test_natural_no_action():
    ctrl = ScenarioController("natural", {}, {})
    for m in range(1, 13):
        a = ctrl.get_action(1, m)
        assert not a.apply_fertilizer
        assert not a.apply_lime


def test_fertilizer_only_months():
    ctrl = ScenarioController("fertilizer", FERT, LIME)
    for m in range(1, 13):
        a = ctrl.get_action(1, m)
        if m in (3, 6, 9):
            assert a.apply_fertilizer
            assert a.n_amount == 12.0
            assert a.p2o5_amount == 4.0
            assert a.k2o_amount == 9.0
        else:
            assert not a.apply_fertilizer
        assert not a.apply_lime  # fertilizer 情景不加石灰


def test_fertilizer_lime_months():
    ctrl = ScenarioController("fertilizer_lime", FERT, LIME)
    a = ctrl.get_action(1, 3)
    assert a.apply_fertilizer
    assert a.apply_lime
    assert a.lime_amount == 45.0


def test_fertilizer_lime_off_months():
    ctrl = ScenarioController("fertilizer_lime", FERT, LIME)
    a = ctrl.get_action(1, 1)
    assert not a.apply_fertilizer
    assert not a.apply_lime


def test_precip_increase_no_actions():
    ctrl = ScenarioController("precip_increase", FERT, LIME)
    for m in range(1, 13):
        a = ctrl.get_action(1, m)
        assert not a.apply_fertilizer
        assert not a.apply_lime


def test_temp_increase_no_actions():
    ctrl = ScenarioController("temp_increase", FERT, LIME)
    for m in range(1, 13):
        a = ctrl.get_action(1, m)
        assert not a.apply_fertilizer
        assert not a.apply_lime
