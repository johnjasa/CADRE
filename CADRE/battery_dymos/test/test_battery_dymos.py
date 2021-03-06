from __future__ import print_function

import unittest

import numpy as np

from openmdao.api import Problem, IndepVarComp, Group
from openmdao.utils.assert_utils import assert_rel_error, assert_check_partials

from CADRE.battery_dymos import BatterySOCComp

class TestBatteryDymos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        nn = 6

        cls.p = Problem(model=Group())

        ivc = cls.p.model.add_subsystem('ivc', IndepVarComp(), promotes_outputs=['*'])
        ivc.add_output('temperature', val=np.ones((nn,5)))
        ivc.add_output('P_bat', val=np.ones((nn,)))
        ivc.add_output('SOC', val=np.ones((nn,)))

        cls.p.model.add_subsystem('battery_soc_comp', BatterySOCComp(num_nodes=nn),
                                  promotes_inputs=['*'], promotes_outputs=['*'])

        cls.p.setup(check=True, force_alloc_complex=True)

        cls.p['temperature'] = 273 + np.random.rand(nn, 5) * 100
        cls.p['P_bat'] = np.random.rand(nn) * 100
        cls.p['SOC'] = np.random.rand(nn)

        cls.p.run_model()

    def test_results(self):
        self.assertTrue(np.all(self.p['dXdt:SOC'] < 0))

    def test_partials(self):
        np.set_printoptions(linewidth=1024)
        cpd = self.p.check_partials(method='cs')
        assert_check_partials(cpd)
