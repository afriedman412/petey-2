"""The simple-names bench's subject comparison (eval/simple_names_bench.py): the kind of value, numbers, column
letters and filler left out of both sides; abbreviations, acronyms and word forms matched."""
import pytest

import simple_names_bench as B


@pytest.mark.parametrize("a, b, want", [
    ("first_name", "first_nm", "same"),                                    # the suffix is not the subject
    ("gross_rents_amt_3", "property_c_gross_rents_amt", "nested"),        # iteration, column letter, table prefix
    ("combined_single_limit_3", "csl_premium_1_amt", "nested"),            # acronym, and the premium word missing
    ("date_leased_1", "vehicle_1_lease_dt", "nested"),                    # leased ~ lease
    ("rental_reimbursement_veh1_num", "transportation_expense_vehicle_1_nbr", "overlap"),
    ("q2_description", "special_equipment_desc_1_txt", "different"),      # says nothing of the subject
    ("applicant_name", "insured_nm", "different"),
])
def test_subject_class(a, b, want):
    assert B.subject_class(a, b) == want
