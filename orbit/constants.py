"""Physical and system constants.

Values that appear in more than one place live here so that a figure and the paper
cannot disagree about the speed of light. Anything with a source has the source in
the comment; anything without one is a project convention, not a measurement.
"""

# -- physics ----------------------------------------------------------------
C = 299_792_458.0            # m/s, exact by definition of the metre
MU_EARTH = 3.986_004_418e14  # m^3/s^2, WGS-84 geocentric gravitational constant
R_EARTH = 6_371_000.0        # m, mean radius (WGS-84 mean; equatorial is 6378 km)

# -- the two bands under study ----------------------------------------------
# S-band is the primary: it is what the srsRAN link runs at, and it is the regime
# the SatNOGS validation data lives near. Ka is the analytical secondary, kept
# because the Doppler rate is fourteen times higher and that is where the tier
# assignment is expected to come under strain.
BANDS = {
    "s":  {"fc_hz": 2.0e9,  "label": "S-band 2 GHz"},
    "ka": {"fc_hz": 28.0e9, "label": "Ka-band 28 GHz"},
}

# -- 5G NR numerology -------------------------------------------------------
# Slot duration and the HARQ round-trip budget follow from the subcarrier spacing.
# 16 HARQ processes is the NR maximum for downlink; the budget is what sets the
# delay at which the day-5 sweep is expected to break.
SCS_HZ = {15: 15_000.0, 30: 30_000.0}
SLOT_S = {15: 1.0e-3, 30: 0.5e-3}
N_HARQ = 16

# Fraction of the subcarrier spacing that residual carrier frequency offset is
# allowed to occupy. 2 % is the working convention in this lab, chosen because it
# keeps inter-carrier interference well below the noise floor at the SNRs seen
# here. It is a project convention. Where it appears in a figure, the figure says so.
CFO_BUDGET_FRACTION = 0.02

# -- the reference orbit ----------------------------------------------------
# 600 km is the altitude the plan's sanity anchors were derived for. A TLE-driven
# run overrides this; the analytic model uses it as a default.
DEFAULT_ALTITUDE_M = 600_000.0
