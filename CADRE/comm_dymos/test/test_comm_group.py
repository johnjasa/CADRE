from __future__ import print_function, division, absolute_import

import unittest

import numpy as np

from openmdao.api import Problem, Group, IndepVarComp
from openmdao.utils.assert_utils import assert_check_partials

from CADRE.comm_dymos.comm_group import CommGroup

GM = 398600.44
rmag = 7000.0
period = 2 * np.pi * np.sqrt(rmag ** 3 / GM)
vcirc = np.sqrt(GM / rmag)
duration = period / 1
delta_trua = 2 * np.pi * (duration / period)

class TestCommGroup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        nn = 10

        p = cls.p = Problem(model=Group())

        ivc = p.model.add_subsystem('ivc', IndepVarComp(), promotes_outputs=['*'])

        ivc.add_output('time', val=np.ones(nn), units='s')
        ivc.add_output('r_e2b_I', val=np.zeros((nn, 3)), units='km')
        ivc.add_output('antAngle', val=np.zeros((nn,)), units='deg')
        ivc.add_output('P_comm', val=np.zeros((nn,)), units='W')
        ivc.add_output('O_BI', val=np.zeros((nn, 3, 3)))

        p.model.add_subsystem('comm_group',
                              CommGroup(num_nodes=nn, lat_gs=0.01, lon_gs=0.0, alt_gs=0.0))

        p.model.connect('time', 'comm_group.t')
        p.model.connect('r_e2b_I', 'comm_group.r_e2b_I')
        p.model.connect('antAngle', 'comm_group.antAngle')
        p.model.connect('P_comm', 'comm_group.P_comm')
        p.model.connect('O_BI', 'comm_group.O_BI')

        p.setup(check=True, force_alloc_complex=True)

        p['time'] = np.linspace(0, 5400, nn)
        trua = delta_trua * p['time']

        p['r_e2b_I'][:, 0] = 6578.137 * np.cos(trua)
        p['r_e2b_I'][:, 1] = 6578.137 * np.sin(trua)
        p['r_e2b_I'][:, 2] = 0.0

        p['antAngle'] = 0.0
        p['P_comm'] = 10.0

        # For testing purposes just fix the body to the ECI frame
        p['O_BI'][:, 0, 0] = 1.0
        p['O_BI'][:, 1, 1] = 1.0
        p['O_BI'][:, 2, 2] = 1.0

        p.run_model()

    def test_partials(self):
        np.set_printoptions(linewidth=100000, edgeitems=10000)
        cpd = self.p.check_partials(method='fd', step=1.0E-6, step_calc='abs')
        assert_check_partials(cpd, atol=2.0E-5, rtol=1.0E-5)

