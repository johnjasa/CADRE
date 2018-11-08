from __future__ import print_function, division, absolute_import

from openmdao.api import Group, VectorMagnitudeComp

from dymos import declare_state, declare_time, declare_parameter

from .orbit_eom import OrbitEOMComp
from .battery_dymos import BatterySOCComp


@declare_time(units='s')
@declare_state('r_e2b_I', rate_source='orbit_eom_comp.dXdt:r_e2b_I', targets=['r_e2b_I'],
               units='km', shape=(3,))
@declare_state('v_e2b_I', rate_source='orbit_eom_comp.dXdt:v_e2b_I', targets=['v_e2b_I'],
               units='km/s', shape=(3,))
@declare_state('SOC', rate_source='battery_soc_comp.dXdt:SOC', targets=['SOC'])
@declare_parameter('T_bat', targets=['T_bat'], units='degK')
@declare_parameter('P_bat', targets=['P_bat'], units='W')
class CadreODE(Group):

    def initialize(self):
        self.options.declare('num_nodes', types=(int,))

    def setup(self):
        nn = self.options['num_nodes']

        self.add_subsystem('rmag_comp',
                           VectorMagnitudeComp(vec_size=nn, length=3, in_name='r_e2b_I',
                                               mag_name='rmag_e2b', units='km'),
                           promotes_inputs=['r_e2b_I'], promotes_outputs=['rmag_e2b'])

        self.add_subsystem('orbit_eom_comp', OrbitEOMComp(num_nodes=nn),
                           promotes_inputs=['rmag_e2b', 'r_e2b_I', 'v_e2b_I'])

        self.add_subsystem('battery_soc_comp', BatterySOCComp(num_nodes=nn),
                           promotes_inputs=['SOC', 'P_bat', 'T_bat'])