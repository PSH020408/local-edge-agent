"""Tests for the engineering calculator and unit conversion.

Run: python -m unittest discover -s tests -v
"""

import unittest

from agent import ToolRegistry
from agent.math_tools import register_math_tools


class MathToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = ToolRegistry()
        register_math_tools(cls.r)

    def calc(self, expression):
        return self.r.call("calculator", {"expression": expression})

    def conv(self, value, from_unit, to_unit):
        return self.r.call("convert_units", {"value": value, "from_unit": from_unit, "to_unit": to_unit})

    # calculator: basics and formatting
    def test_arithmetic_and_formatting(self):
        self.assertEqual(self.calc("(12.5 * 4) / 2"), "25")
        self.assertEqual(self.calc("1847*293/3"), "180390.333333")
        self.assertEqual(self.calc("2**128"), str(2**128))

    def test_functions(self):
        self.assertEqual(self.calc("sqrt(3**2 + 4**2)"), "5")
        self.assertEqual(self.calc("log(8, 2)"), "3")
        self.assertEqual(self.calc("comb(45, 6)"), "8145060")
        self.assertEqual(self.calc("max([3, 9, 4])"), "9")
        self.assertEqual(self.calc("round(pi, 4)"), "3.1416")

    def test_degrees_vs_radians(self):
        self.assertEqual(self.calc("sind(30)"), "0.5")
        self.assertEqual(self.calc("sin(pi/6)"), "0.5")
        self.assertEqual(self.calc("atand(1)"), "45")

    def test_inverse_trig_also_reports_degrees(self):
        # Run 6: 14B converted atan() radians to degrees in its head and was off by 0.01.
        out = self.calc("atan(2 * pi * 60 * 0.05 / 100)")
        self.assertEqual(out, "0.186309524071 radians = 10.6747494124 degrees")
        self.assertEqual(self.calc("atand(1)"), "45")
        self.assertEqual(self.calc("2 * atan(1)"), "1.57079632679")

    # Run 7 failures
    def test_sequences_for_long_products(self):
        # Birthday problem: the model listed the factors by hand and missed two.
        expected = "0.507297234324"
        self.assertEqual(self.calc("1 - prod(seq(343, 365)) / 365**23"), expected)
        self.assertEqual(self.calc("1 - perm(365, 23) / 365**23"), expected)
        self.assertEqual(self.calc("len(seq(343, 365))"), "23")
        self.assertEqual(self.calc("sum(seq(1, 100))"), "5050")
        self.assertIn("Error", self.calc("seq(1, 10**9)"))

    # Run 8: "...", "product(...)" and loop syntax before reaching prod(seq(...))
    def test_ellipsis_and_loops_point_to_seq(self):
        out = self.calc("1 - (365/365) * (364/365) * (363/365) * ... * (343/365)")
        self.assertIn("prod(seq(start, end))", out)
        out = self.calc("1 - product(365 - i)/365 for i in 0..21")
        self.assertIn("loops are not supported", out)
        self.assertIn("prod(seq(start, end))", out)

    def test_function_aliases(self):
        self.assertTrue(self.calc("1 - product(seq(365 - 22, 365 - 0)) / (365^23)").startswith("0.507297234324"))
        self.assertEqual(self.calc("mean([2, 4, 9])"), "5")
        self.assertEqual(self.calc("average(2, 4, 9)"), "5")
        self.assertEqual(self.calc("arctan(1) * 4"), "3.14159265359")
        self.assertEqual(self.calc("nCr(45, 6)"), "8145060")
        self.assertIn("= 2 m", self.qty("square_root(4 m**2)", "m"))

    # Run 9 failures (14B)
    def test_lists_work_element_by_element(self):
        expected = "[0.659001138886, 0.242432970705, 0.0985658904093]"
        self.assertEqual(self.calc("exp([2.0, 1.0, 0.1]) / sum(exp([2.0, 1.0, 0.1]))"), expected)
        self.assertEqual(self.calc("[exp(2.0), exp(1.0), exp(0.1)] / (exp(2.0) + exp(1.0) + exp(0.1))"), expected)
        self.assertEqual(self.calc("round([0.6591, 0.2424], 2)"), "[0.66, 0.24]")
        self.assertEqual(self.calc("[1, 2, 3] * [4, 5, 6]"), "[4, 10, 18]")
        self.assertEqual(self.calc("sum([1, 2, 3] ** 2)"), "14")
        self.assertIn("same length", self.calc("[1, 2] + [1, 2, 3]"))

    def test_loop_variable_points_to_seq(self):
        out = self.calc("1 - product(seq(365 - i, i, 0, 22)) / 365**23")
        self.assertIn("prod(seq(start, end))", out)

    def test_variables_get_a_clear_hint(self):
        self.assertIn("Variables are not supported", self.calc("-R * C * ln(1 - 0.9)"))

    def test_misplaced_argument_points_to_the_right_tool(self):
        out = self.r.call("calculator", {"expression": "50e3 / (pi * 0.01**2)", "to_unit": "MPa"})
        self.assertIn("Tools that accept ['to_unit']: calculate_with_units", out)

    def test_convert_units_accepts_a_formula_value(self):
        out = self.conv("50e3 / (pi * 0.01**2)", "Pa", "MPa")
        self.assertIn("= 159.154943092 MPa", out)

    def test_stress_with_units(self):
        self.assertIn("= 159.154943092 MPa", self.qty("50 kN / (pi * (10 mm)**2)", "MPa"))

    def test_decibels(self):
        self.assertEqual(self.calc("db(2)"), "3.01029995664")
        self.assertEqual(self.calc("dbm_to_watts(30)"), "1")
        self.assertEqual(self.calc("watts_to_dbm(0.001)"), "0")

    def test_complex_numbers(self):
        out = self.calc("(3+4j)")
        self.assertIn("3 + 4j", out)
        self.assertIn("magnitude 5", out)
        self.assertIn("1.41421356237j", self.calc("sqrt(-2)"))
        self.assertIn("magnitude 10, angle 30 degrees", self.calc("phasor(10, 30)"))

    def test_bases_and_bits(self):
        self.assertEqual(self.calc("to_base(255, 16)"), "0xff")
        self.assertEqual(self.calc("from_base('1011', 2)"), "11")
        self.assertEqual(self.calc("xor(6, 3)"), "5")
        self.assertEqual(self.calc("1 << 10"), "1024")

    def test_physical_constants(self):
        self.assertEqual(self.calc("speed_of_light"), "299792458")
        self.assertEqual(self.calc("standard_gravity * 10"), "98.0665")

    # calculator: safety
    def test_rejects_code(self):
        self.assertIn("Error", self.calc("__import__('os').system('ls')"))
        self.assertIn("Error", self.calc("open('x')"))
        self.assertIn("Error", self.calc("(1).__class__"))

    def test_caret_means_power_for_plain_numbers(self):
        # Run 6: "10^(30/10)" and "100^2" meant powers.
        self.assertTrue(self.calc("2^3").startswith("8 (note: ^ was read as power"))
        self.assertTrue(self.calc("sqrt(3^2 + 4^2)").startswith("5 "))
        self.assertTrue(self.calc("10^(30/10)").startswith("1000 "))

    def test_caret_means_xor_next_to_bit_literals(self):
        # Run 6 (after the first fix): "0xFF ^ 0b1010" meant XOR and returned 255**10.
        self.assertTrue(self.calc("0xFF ^ 0b1010").startswith("245 (note: ^ was read as bitwise XOR"))
        self.assertEqual(self.calc("xor(6, 3)"), "5")
        self.assertEqual(self.calc("0xFF ** 2"), "65025")

    def test_units_in_calculator_point_to_unit_tool(self):
        self.assertIn("calculate_with_units", self.calc("(100 km/h - 0) / 8 s"))

    def test_rejects_huge_numbers(self):
        self.assertIn("Error", self.calc("2**100000"))
        self.assertIn("Error", self.calc("factorial(5000)"))

    # convert_units
    def test_common_conversions(self):
        self.assertIn("= 27.7777777778 m/s", self.conv(100, "km/h", "m/s"))
        self.assertIn("= 1.609344 km", self.conv(1, "mile", "km"))
        self.assertIn("= 101325 Pa", self.conv(1, "atm", "Pa"))
        self.assertIn("= 1024 MiB", self.conv(1, "GiB", "MiB"))

    def test_temperature(self):
        self.assertIn("= 77 degF", self.conv(25, "degC", "degF"))
        self.assertIn("= 100 ℃", self.conv(212, "°F", "℃"))
        self.assertIn("= -273.15 degC", self.conv(0, "K", "degC"))

    def test_engineering_units(self):
        self.assertIn("= 50.9858106489 kgf*cm", self.conv(5, "N*m", "kgf*cm"))
        self.assertIn("= 0.745699871582 kW", self.conv(1, "hp", "kW"))

    def test_korean_units(self):
        self.assertIn("= 105.785123967 m**2", self.conv(32, "pyeong", "m**2"))
        self.assertIn("= 600 g", self.conv(1, "근", "g"))

    # calculate_with_units
    def qty(self, expression, to_unit=""):
        return self.r.call("calculate_with_units", {"expression": expression, "to_unit": to_unit})

    def test_formulas_with_units(self):
        self.assertIn("= 3.47222222222 m/s²", self.qty("(100 km/h - 0) / 8 s", "m/s**2"))
        self.assertIn("= 19.6133 N", self.qty("2 kg * 9.80665 m/s^2", "N"))
        self.assertIn("= 578.703703704 kJ", self.qty("0.5 * 1500 kg * (100 km/h)**2", "kJ"))

    def test_number_unit_pairs_are_grouped(self):
        # Without grouping, pint reads "12 V / 4 ohm" as (12 V / 4) * ohm.
        self.assertIn("= 3 A", self.qty("12 V / 4 ohm", "A"))
        self.assertIn("= 3 A", self.qty("12 V / 4 Ω", "A"))
        self.assertIn("= 1000 m²", self.qty("10 m^2 * 100", "m**2"))

    def test_square_root_and_base_units(self):
        out = self.qty("(2 * 9.80665 m/s**2 * 10 m)**0.5")
        self.assertIn("14.0047491945 m/s", out)

    def test_sqrt_with_units(self):
        # Run 6: the model wrote sqrt(...) inside a unit formula.
        self.assertIn("= 14.0047491945 m/s", self.qty("sqrt(2 * 9.80665 m/s**2 * 10 m)", "m/s"))
        self.assertIn("= 5 m", self.qty("sqrt((3 m)**2 + (4 m)**2)", "m"))

    def test_unit_formula_errors(self):
        self.assertIn("but 'N' is a force (N)", self.qty("2 kg * 3 m", "N"))
        self.assertIn("needs a value without units", self.qty("ln(5 m)"))
        # Run 6: the model put a complex j into a unit formula three times.
        out = self.qty("(100 ohm) + (j * 2 * pi * 60 Hz * 50 mH)", "ohm")
        self.assertIn("complex numbers are not supported with units", out)
        self.assertIn("complex", self.qty("(100 ohm) + (2 * pi * 60 Hz * 50 mH) * 1j", "ohm"))

    # Run 8 failures (RC circuit question)
    def test_kilo_ohm_is_not_boltzmann(self):
        # "kΩ" became "k ohm" and pint read k as the Boltzmann constant.
        self.assertIn("= 0.47 s", self.qty("(10 kΩ) * (47 µF)", "s"))
        self.assertIn("= 0.47 s", self.qty("10kΩ * 47µF", "s"))
        self.assertIn("= 1.08221499371 s", self.qty("(10 kΩ) * (47 µF) * 2.302585092994046", "seconds"))

    def test_functions_inside_unit_formulas(self):
        self.assertIn("= 1.08221499371 s", self.qty("(10 kΩ) * (47 µF) * ln(10 / (100 - 90) * 10)", "seconds"))
        self.assertIn("= 1.08221499371 s", self.qty("-(10 kΩ) * (47 µF) * ln(1 - 0.9)", "s"))
        self.assertIn("= 0.632120558829", self.qty("1 - exp(-(0.47 s) / ((10 kΩ) * (47 µF)))"))
        self.assertIn("= 5 m", self.qty("sqrt((3 m)**2 + (4 m)**2)", "m"))

    def test_letter_variables_in_unit_formula(self):
        # Run 9: "ln(10) * R * C" was read as gas constant * coulomb.
        out = self.qty("ln(10) * R * C", "s")
        self.assertIn("R = the gas constant", out)
        self.assertIn("C = coulomb", out)
        self.assertIn("(10 kΩ) * (47 µF)", out)
        # Real units must not be flagged.
        self.assertEqual("", __import__("agent.math_tools", fromlist=["_variable_hint"])._variable_hint("2 kg * 9.80665 m/s^2"))
        self.assertIn("= 3.47222222222 m/s²", self.qty("(100 km/h - 0) / 8 s", "m/s**2"))

    # Run 10: final holdout test failures
    def test_dimension_errors_use_plain_names(self):
        # 8B computed v**2 / (2d) correctly but asked for m^2/s^2 and repeated the call.
        out = self.qty("((90 km/h) ** 2) / (2 * 40 m)", "m^2/s^2")
        self.assertIn("the formula gives an acceleration (m/s²)", out)
        self.assertIn("energy per mass", out)
        self.assertIn("= 7.8125 m/s²", self.qty("((90 km/h) ** 2) / (2 * 40 m)", "m/s^2"))
        self.assertIn("= 9.375 kN", self.qty("(0.5 * 1200 kg * (90 km/h)^2) / (40 m)", "kN"))

    def test_link_budget_hint_and_answer(self):
        # 8B used 10*log10(2) (dBW) as dBm; 14B treated 2 W as 2 dBm.
        out = self.qty("(2 W) * (10 dBi) - (100 dB) + (3 dBi)", "dBm")
        self.assertIn("watts_to_dbm(2) + 10 + 3 - 100", out)
        out = self.qty("(2 W * 10 dBi * 3 dBi) / 100 dB", "dBm")
        self.assertIn("Decibel values are added", out)
        self.assertEqual(self.calc("watts_to_dbm(2) + 10 + 3 - 100"), "-53.9897000434")
        self.assertEqual(self.calc("watts_to_dbw(2) + 30"), "33.0102999566")
        self.assertIn("= 33.0102999566 dBm", self.conv(2, "W", "dBm"))

    def test_holdout_questions_are_solvable(self):
        self.assertEqual(self.calc("1 / (1/100 + 1/220 + 1/470)"), "59.9767981439")
        self.assertEqual(self.calc("-ln(0.8)"), "0.223143551314")
        self.assertEqual(self.calc("log2(64 * 1024**3)"), "36")
        self.assertEqual(self.calc("comb(10, 3) * (1/6)**3 * (5/6)**7"), "0.155045359574")
        self.assertIn("= 251.16 s", self.qty("(1.5 kg * 4186 J/(kg·K) * (100 °C - 20 °C)) / (2000 W)", "s"))

    def test_errors(self):
        self.assertIn("measure different things", self.conv(1, "kg", "m"))
        self.assertIn("unknown unit", self.conv(1, "kilometerz", "m"))


if __name__ == "__main__":
    unittest.main()
