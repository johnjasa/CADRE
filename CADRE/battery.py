"""
Battery discipline for CADRE
"""

import numpy as np

from openmdao.api import ExplicitComponent
from openmdao.components.ks_comp import KSfunction

from CADRE import rk4


# Constants
sigma = 1e-10
eta = 0.99
Cp = 2900.0*0.001*3600.0
IR = 0.9
T0 = 293.0
alpha = np.log(1/1.1**5)


class BatterySOC(rk4.RK4):
    """
    Computes the time history of the battery state of charge.

    Parameters
    ----------
    n_time: int
        number of time_steps to take

    time_step: float
        size of each timestep
    """

    def __init__(self, n_times, h):
        super(BatterySOC, self).__init__(n_times, h)

        self.n_times = n_times

    def setup(self):
        n_times = self.n_times

        # Inputs
        self.add_input('iSOC', np.zeros((1, )), units=None,
                       desc='Initial state of charge')

        self.add_input('P_bat', np.zeros((n_times, )), units='W',
                       desc='Battery power over time')

        self.add_input('temperature', np.zeros((n_times, 5)), units='degK',
                       desc='Battery temperature over time')

        # Outputs
        self.add_output('SOC', np.zeros((n_times, 1)), units=None,
                        desc='Battery state of charge over time')

        self.options['state_var'] = 'SOC'
        self.options['init_state_var'] = 'iSOC'
        self.options['external_vars'] = ['P_bat', 'temperature']

    def f_dot(self, external, state):
        """
        Rate of change of SOC
        """
        SOC = state[0]
        P = external[0]
        T = external[5]

        voc = 3 + np.expm1(SOC) / (np.e-1)
        # dVoc_dSOC = np.exp(SOC) / (np.e-1)

        V = IR * voc * (2.0 - np.exp(alpha*(T-T0)/T0))
        I = P/V  # noqa: E741

        soc_dot = -sigma/24*SOC + eta/Cp*I

        return soc_dot

    def df_dy(self, external, state):
        """
        State derivative
        """
        SOC = state[0]
        P = external[0]
        T = external[5]

        voc = 3 + np.expm1(SOC) / (np.e-1)
        dVoc_dSOC = np.exp(SOC) / (np.e-1)

        tmp = 2 - np.exp(alpha*(T-T0)/T0)
        V = IR * voc * tmp
        # I = P/V

        dV_dSOC = IR * dVoc_dSOC * tmp
        dI_dSOC = -P/V**2 * dV_dSOC

        df_dy = -sigma/24 + eta/Cp*dI_dSOC

        return np.array([[df_dy]])

    def df_dx(self, external, state):
        """
        Output derivative
        """
        SOC = state[0]
        P = external[0]
        T = external[1]

        voc = 3 + np.expm1(SOC) / (np.e-1)
        # dVoc_dSOC = np.exp(SOC) / (np.e-1)

        tmp = 2 - np.exp(alpha*(T-T0)/T0)

        V = IR * voc * tmp
        # I = P/V

        dV_dT = - IR * voc * np.exp(alpha*(T-T0)/T0) * alpha/T0
        dI_dT = - P/V**2 * dV_dT
        dI_dP = 1.0/V

        return np.array([[eta/Cp*dI_dP, 0, 0, 0, 0, eta/Cp*dI_dT]])


class BatteryPower(ExplicitComponent):
    """
    Power supplied by the battery
    """
    def __init__(self, n=2):
        super(BatteryPower, self).__init__()

        self.n = n

    def setup(self):
        n = self.n

        # Inputs
        self.add_input('SOC', np.zeros((n, )), units=None,
                       desc='Battery state of charge over time')

        self.add_input('temperature', np.zeros((n, 5)), units='degK',
                       desc='Battery temperature over time')

        self.add_input('P_bat', np.zeros((n, )), units='W',
                       desc='Battery power over time')

        # Outputs
        self.add_output('I_bat', np.zeros((n, )), units='A',
                        desc='Battery Current over time')

        row_col = np.arange(n)

        self.declare_partials('I_bat', 'SOC', rows=row_col, cols=row_col)
        self.declare_partials('I_bat', 'P_bat', rows=row_col, cols=row_col)

        col = 5*row_col + 4
        self.declare_partials('I_bat', 'temperature', rows=row_col, cols=col)

    def compute(self, inputs, outputs):
        """
        Calculate outputs.
        """
        SOC = inputs['SOC']
        temperature = inputs['temperature']
        P_bat = inputs['P_bat']

        self.exponential = (2.0 - np.exp(alpha*(temperature[:, 4]-T0)/T0))
        self.voc = 3.0 + np.expm1(SOC) / (np.e-1)
        self.V = IR * self.voc * self.exponential

        outputs['I_bat'] = P_bat / self.V

    def compute_partials(self, inputs, partials):
        """
        Calculate and save derivatives. (i.e., Jacobian)
        """
        SOC = inputs['SOC']
        temperature = inputs['temperature']
        P_bat = inputs['P_bat']

        # dI_dP
        dV_dvoc = IR * self.exponential
        dV_dT = - IR * self.voc * np.exp(alpha*(temperature[:, 4] - T0)/T0) * alpha / T0
        dVoc_dSOC = np.exp(SOC) / (np.e-1)

        partials['I_bat', 'P_bat'] = 1.0 / self.V

        tmp = -P_bat/(self.V**2)
        partials['I_bat', 'temperature'] = tmp * dV_dT
        partials['I_bat', 'SOC'] = tmp * dV_dvoc * dVoc_dSOC


class BatteryConstraints(ExplicitComponent):
    """
    Some KS constraints for the battery. I believe this essentially
    replaces a cycle in the graph.
    """

    def __init__(self, n=2):
        super(BatteryConstraints, self).__init__()
        self.n = n

        self.rho = 50
        self.Imin = -10.0
        self.Imax = 5.0
        self.SOC0 = 0.2
        self.SOC1 = 1.0

        self.KS_ch = KSfunction()
        self.KS_ds = KSfunction()
        self.KS_s0 = KSfunction()
        self.KS_s1 = KSfunction()

    def setup(self):
        n = self.n

        # Inputs
        self.add_input('I_bat', np.zeros((n, )), units='A',
                       desc='Battery current over time')

        self.add_input('SOC', np.zeros((n, )), units=None,
                       desc='Battery state of charge over time')

        # Outputs
        self.add_output('ConCh', 0.0, units='A',
                        desc='Constraint on charging rate')

        self.add_output('ConDs', 0.0, units='A',
                        desc='Constraint on discharging rate')

        self.add_output('ConS0', 0.0, units=None,
                        desc='Constraint on minimum state of charge')

        self.add_output('ConS1', 0.0, units=None,
                        desc='Constraint on maximum state of charge')

        self.declare_partials('ConCh', 'I_bat')
        self.declare_partials('ConDs', 'I_bat')
        self.declare_partials('ConS0', 'SOC')
        self.declare_partials('ConS1', 'SOC')

    def compute(self, inputs, outputs):
        """
        Calculate outputs.
        """
        I_bat = inputs['I_bat']
        SOC = inputs['SOC']

        outputs['ConCh'] = self.KS_ch.compute(I_bat - self.Imax, self.rho)
        outputs['ConDs'] = self.KS_ds.compute(self.Imin - I_bat, self.rho)
        outputs['ConS0'] = self.KS_s0.compute(self.SOC0 - SOC, self.rho)
        outputs['ConS1'] = self.KS_s1.compute(SOC - self.SOC1, self.rho)

    def compute_partials(self, inputs, partials):
        """
        Calculate and save derivatives. (i.e., Jacobian)
        """
        dCh_dg, _ = self.KS_ch.derivatives()
        dDs_dg, _ = self.KS_ds.derivatives()
        dS0_dg, _ = self.KS_s0.derivatives()
        dS1_dg, _ = self.KS_s1.derivatives()

        partials['ConCh', 'I_bat'] = dCh_dg
        partials['ConDs', 'I_bat'] = -dDs_dg
        partials['ConS0', 'SOC'] = -dS0_dg
        partials['ConS1', 'SOC'] = dS1_dg
