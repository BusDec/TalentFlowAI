"""Update NEEPCO/02/2026 seed data with the REAL content from the published PDF.

Fills the advertisement with the exact company profile, boilerplate sections and
post details from the official NEEPCO advertisement so generated output matches
the source document.
"""

from django.core.management.base import BaseCommand

from recruitment.boilerplate import (
    DEFAULT_CONTACT_EMAIL,
    DEFAULT_FEE_TEXT,
    DEFAULT_GENERAL_CONDITIONS,
    DEFAULT_HEALTH_TEXT,
    DEFAULT_HOW_TO_APPLY,
    DEFAULT_LOCATION,
    DEFAULT_PERIOD,
)
from recruitment.models import Advertisement


REAL_PROFILE = """North Eastern Electric Power Corporation Limited, (an equal opportunity employer) a Schedule –'A' "Mini Ratna" CPSE (Central Public Sector Enterprise) and a Wholly Owned Subsidiary of NTPC, has been a trusted power generation Company in the North Eastern Region of India and beyond since 1976, working under the Ministry of Power for the Country as a whole and specially for the north eastern states to act in their best interest in tapping the enormous power potential of the region and the country.

NEEPCO takes pride in operating the largest Hydro Power Plant in the North Eastern Region of the Country and being the only CPSU having Hydro, Gas Based and Renewable Power Stations in operation. NEEPCO is having exposure in planning, design & construction & operation of Hydro projects in highly difficult and Geo-Technically sensitive terrain of N.E. Region."""

POST_DETAILS = {
    "FTB/5/HR/49": {
        "name": "Executive (ERP)",
        "vacancies": 2, "max_age": 37, "category": {"ur": 2},
        "qualification": ("Full- time Bachelor in Engineering / Bachelor in Technology / BSc. Engineering (in any field) "
                          "from recognized University. SAP certification in HCM module (SAP Certified Application "
                          "Associate – SAP HCM or SAP Success Factors Employee Central) is mandatory. Additional "
                          "qualification in HR/Personnel Management (MBA/PG Diploma) will be an advantage."),
        "experience": ("Minimum 7 years post-qualification experience. Core Experience (Must have): Hands-on experience "
                       "in SAP ERP HCM module implementation/support/rollout; End-to-end implementation experience of "
                       "at least 2 full-cycle SAP HCM projects; Expertise in configuration and support of Personnel "
                       "Administration (PA), Organizational Management (OM), Time Management (TM), Payroll (India), "
                       "and ESS/MSS; Integration knowledge with Finance (FI), Materials Management (MM), and Project "
                       "Systems (PS) modules; Should have led or played a significant role in data migration, system "
                       "testing (UT, IT, UAT), cutover, and go-live support."),
        "pay_scale": "Rs 1,66,000/-",
    },
    "FTB/5/HR/173": {
        "name": "Executive (HR) (Corporate Communication)",
        "vacancies": 1, "max_age": 37, "category": {"ur": 1},
        "qualification": ("Graduate with PG Degree / Diploma in Mass Communication / Journalism (2 yrs full time "
                          "course) recognized by Government of India."),
        "experience": ("Minimum 7 years of experience in relevant fields: managing public relations/corporate "
                       "communication function; skills in media planning, press relations, and content creation for "
                       "various media (radio, television, print, and social media); communication & interpersonal "
                       "skills; ability to research topics, gather information, verify facts, and analyze data; "
                       "creativity & adaptability; branding; knowledge management systems."),
        "pay_scale": "Rs 1,66,000/-",
    },
    "FTB/5/HR/12": {
        "name": "Executive (Civil)",
        "vacancies": 3, "max_age": 37, "category": {"ur": 3},
        "qualification": ("Full time Bachelor Degree in Civil Engineering from a recognized University/ Institute of India."),
        "experience": ("7 years of post-qualification experience in planning/ survey & investigation/ civil construction "
                       "works of Hydropower project/ PSP. Preference for candidates with experience in: DPR preparation "
                       "of Hydro / PSP projects; Survey & investigation works. Knowledge of CEA Guidelines for "
                       "preparation of DPR for Hydro power project/ PSP is mandatory. Proficiency in working in SAP "
                       "(S/4 HANA), report writing and technical documentation required."),
        "pay_scale": "Rs 1,66,000/-",
    },
    "FTB/4/HR/13": {
        "name": "Executive (Civil)",
        "vacancies": 3, "max_age": 34, "category": {"ur": 2, "obc": 1},
        "qualification": ("Full time Bachelor Degree in Civil Engineering from a recognized University /Institute of India."),
        "experience": ("04 years of post-qualification experience in Hydropower project/ PSP. Preference for candidates "
                       "with experience in: Survey & investigation works of hydro power project/ PSP; DPR preparation "
                       "for Hydro power project / PSP. Proficiency in working in SAP (S/4 HANA), report writing and "
                       "technical documentation required."),
        "pay_scale": "Rs 1,45,000/-",
    },
    "FTB/1/HR/21": {
        "name": "Executive (Civil)",
        "vacancies": 3, "max_age": 30, "category": {"ur": 1, "sc": 1, "obc": 1},
        "qualification": ("Full time Bachelor Degree/ 3 years Diploma in Civil Engineering from a recognized "
                          "University/ Institute of India."),
        "experience": ("For candidates having bachelor's degree in Civil Engineering: 01 year of post-qualification "
                       "experience in Survey & Investigation works of hydro power project/PSP. For candidates having "
                       "diploma in Civil Engineering: 05 years of post-qualification experience in Survey & "
                       "Investigation works of hydro power project/ PSP. Proficiency in working in SAP (S/4 HANA), "
                       "report writing and technical documentation required."),
        "pay_scale": "Rs 71,000/-",
    },
    "FTB/4/HR/291": {
        "name": "Executive (Security)",
        "vacancies": 4, "max_age": 34, "category": {"ur": 2, "sc": 1, "obc": 1},
        "qualification": ("Graduate in any discipline, recognized by Govt. of India."),
        "experience": ("Minimum 9 years of experience in Armed Forces in the rank of Captain / Major/ Lieutenant "
                       "Colonel or in the rank of DSP/ SP or equivalent in Central/ State Police Organizations, with "
                       "experience in different areas of overall Security System."),
        "pay_scale": "Rs 1,45,000/-",
    },
    "FTB/4/HR/183": {
        "name": "Executive (Law)",
        "vacancies": 1, "max_age": 34, "category": {"ur": 1},
        "qualification": ("Bachelor's Degree in Law (LLB or equivalent- full time degree from recognized Indian "
                          "University/ Institute)."),
        "experience": ("6 yrs practice in Court of Law as Advocate or Judicial Service or in CPSU / represent the PSU "
                       "in the Court of Law or 9 yrs experience in the next below grade in CPSU / GOI / State Govt."),
        "pay_scale": "Rs 1,45,000/-",
    },
    "FTB/4/HR/83": {
        "name": "Executive (Safety)",
        "vacancies": 2, "max_age": 34, "category": {"ur": 2},
        "qualification": ("Engineering Degree in Mechanical/ Electrical/ Production from a recognized University/ "
                          "Institution with a full time Diploma in Industrial Safety from Regional Labour Institute/ "
                          "Institution recognized under the Factories Act/ Rules or Engineering Degree in Industrial "
                          "Safety/ Fire & Safety from a University / Institution recognized under the Factories Act/ Rules."),
        "experience": ("Minimum 04 years working experience in compliance with safety regulations under the Factories "
                       "Act. Developing, auditing and improving safety systems. Promotion of safety consciousness "
                       "amongst employees and examination of machinery, equipment and building from the safety angle. "
                       "Experience in organizing safety training and firefighting would be an added advantage. Post "
                       "qualification experience in relevant area shall be counted from the date a candidate has "
                       "acquired the Degree in Engineering."),
        "pay_scale": "Rs 1,45,000/-",
    },
    "FTB/4/HR/257": {
        "name": "Executive (Finance)",
        "vacancies": 6, "max_age": 34, "category": {"ur": 5, "obc": 1},
        "qualification": ("Graduate with CA/CMA or MBA or equivalent with specialization in Finance of at least two "
                          "years duration recognized by GOI."),
        "experience": "Minimum 4 years of experience in the relevant field.",
        "pay_scale": "Rs 1,45,000/-",
    },
    "FTB/2/HR/256": {
        "name": "Executive (Finance)",
        "vacancies": 6, "max_age": 30, "category": {"ur": 2, "sc": 1, "obc": 2, "ews": 1},
        "qualification": ("Graduate with CA/CMA or MBA or equivalent with specialization in Finance of at least two "
                          "years duration recognized by GOI."),
        "experience": "As per advertisement.",
        "pay_scale": "Rs 90,000/-",
    },
    "FTB/3/HR/280": {
        "name": "Executive (Medical)",
        "vacancies": 5, "max_age": 31, "category": {"ur": 4, "obc": 1},
        "qualification": ("MBBS preferably with Post graduate Degree / Diploma in one of areas of Medical Science (+) "
                          "Registered with the Indian Medical Council."),
        "experience": ("Preferable 1 year of experience in large industry / reputed Hospital after completion of "
                       "Internship. He or she will be executing duties under a doctor of the corporation or as "
                       "independent in charge of the Health Centre Dispensary in stations of the company in project "
                       "locations of North East. Required to perform with a minimum desired level of competence and "
                       "should be able to handle basic medical emergencies. Required to comply with all statutory "
                       "guidelines and laws in the purview of the Medical Wing."),
        "pay_scale": "Rs 1,35,000/-",
    },
    "FTB/2/HR/159": {
        "name": "Executive (HR) (CSR)",
        "vacancies": 2, "max_age": 30, "category": {"ur": 2},
        "qualification": ("A Master's Degree in Social Work, Community Organisation and Development Practice, "
                          "recognized by GOI."),
        "experience": ("1 (one) year experience in CSR/ Social Welfare works in any reputed organization (Govt/ "
                       "Private). Experience of working in ERP Environment."),
        "pay_scale": "Rs 90,000/-",
    },
}


class Command(BaseCommand):
    help = "Populate NEEPCO/02/2026 with the real content from the published advertisement PDF"

    def handle(self, *args, **options):
        advt = Advertisement.objects.filter(advt_number="NEEPCO/02/2026").first()
        if not advt:
            self.stdout.write(self.style.WARNING("NEEPCO/02/2026 not found. Run simulate_neepco_advt first."))
            return

        advt.company_name = "North Eastern Electric Power Corporation Limited"
        advt.company_tagline = "(A Government of India Enterprise)"
        advt.company_address = "Brookland Compound, Lower New Colony, Shillong – 793003, Meghalaya"
        advt.contact_email = DEFAULT_CONTACT_EMAIL
        advt.description = REAL_PROFILE
        advt.registration_fee_text = DEFAULT_FEE_TEXT
        advt.health_text = DEFAULT_HEALTH_TEXT
        advt.general_conditions = DEFAULT_GENERAL_CONDITIONS
        advt.how_to_apply = DEFAULT_HOW_TO_APPLY
        advt.save()

        updated = 0
        # Map the simulator's placeholder codes to the real NEEPCO codes.
        CODE_FIX = {
            "FTB/CSR/01": "FTB/2/HR/159",
            "FTB/LAW/01": "FTB/4/HR/183",
            "FTB/MED/01": "FTB/3/HR/280",
            "FTB/SAF/01": "FTB/4/HR/83",
            "FTB/SEC/01": "FTB/4/HR/291",
        }
        used_codes = set(advt.posts.values_list("post_code", flat=True))

        for post in advt.posts.all():
            details = POST_DETAILS.get(post.post_code)
            new_code = post.post_code

            if not details:
                # Fix placeholder code -> real code.
                new_code = CODE_FIX.get(post.post_code)
                details = POST_DETAILS.get(new_code) if new_code else None

            if not details:
                continue

            if new_code and new_code != post.post_code:
                if new_code in used_codes and new_code not in (post.post_code,):
                    # Target code already exists as another row — skip to avoid
                    # unique-together violation.
                    self.stdout.write(self.style.WARNING(f"  Skipped {post.post_code}: {new_code} already exists."))
                    continue
                used_codes.discard(post.post_code)
                used_codes.add(new_code)
                post.post_code = new_code

            post.name = details["name"]
            post.vacancies = details["vacancies"]
            post.max_age = details["max_age"]
            post.qualification = details["qualification"]
            post.experience_required = details["experience"]
            post.pay_scale = details["pay_scale"]
            post.category_breakup = details["category"]
            post.location = DEFAULT_LOCATION
            post.period_of_engagement = DEFAULT_PERIOD
            post.save()
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Updated advertisement {advt.advt_number}: profile + {updated} posts with real NEEPCO content."
        ))
