import logging
from faker import Faker

from registrar.models import (
    User,
    UserGroup,
)

fake = Faker()
logger = logging.getLogger(__name__)


class UserFixture:
    """
    Load users into the database.

    Make sure this class' `load` method is called from `handle`
    in management/commands/load.py, then use `./manage.py load`
    to run this code.
    """

    ADMINS = [
        {
            "username": "5f283494-31bd-49b5-b024-a7e7cae00848",
            "first_name": "Rachid",
            "last_name": "Mrad",
        },
        {
            "username": "eb2214cd-fc0c-48c0-9dbd-bc4cd6820c74",
            "first_name": "Alysia",
            "last_name": "Broddrick",
        },
        {
            "username": "8f8e7293-17f7-4716-889b-1990241cbd39",
            "first_name": "Katherine",
            "last_name": "Osos",
        },
        {
            "username": "70488e0a-e937-4894-a28c-16f5949effd4",
            "first_name": "Gaby",
            "last_name": "DiSarli",
        },
        {
            "username": "83c2b6dd-20a2-4cac-bb40-e22a72d2955c",
            "first_name": "Cameron",
            "last_name": "Dixon",
        },
        {
            "username": "0353607a-cbba-47d2-98d7-e83dcd5b90ea",
            "first_name": "Ryan",
            "last_name": "Brooks",
        },
        {
            "username": "30001ee7-0467-4df2-8db2-786e79606060",
            "first_name": "Zander",
            "last_name": "Adkinson",
        },
        {
            "username": "2bf518c2-485a-4c42-ab1a-f5a8b0a08484",
            "first_name": "Paul",
            "last_name": "Kuykendall",
        },
        {
            "username": "2a88a97b-be96-4aad-b99e-0b605b492c78",
            "first_name": "Rebecca",
            "last_name": "Hsieh",
        },
        {
            "username": "fa69c8e8-da83-4798-a4f2-263c9ce93f52",
            "first_name": "David",
            "last_name": "Kennedy",
        },
        {
            "username": "f14433d8-f0e9-41bf-9c72-b99b110e665d",
            "first_name": "Nicolle",
            "last_name": "LeClair",
        },
    ]

    STAFF = [
        {
            "username": "319c490d-453b-43d9-bc4d-7d6cd8ff6844",
            "first_name": "Rachid-Analyst",
            "last_name": "Mrad-Analyst",
            "email": "rachid.mrad@gmail.com",
        },
        {
            "username": "b6a15987-5c88-4e26-8de2-ca71a0bdb2cd",
            "first_name": "Alysia-Analyst",
            "last_name": "Alysia-Analyst",
        },
        {
            "username": "91a9b97c-bd0a-458d-9823-babfde7ebf44",
            "first_name": "Katherine-Analyst",
            "last_name": "Osos-Analyst",
            "email": "kosos@truss.works",
        },
        {
            "username": "2cc0cde8-8313-4a50-99d8-5882e71443e8",
            "first_name": "Zander-Analyst",
            "last_name": "Adkinson-Analyst",
        },
        {
            "username": "57ab5847-7789-49fe-a2f9-21d38076d699",
            "first_name": "Paul-Analyst",
            "last_name": "Kuykendall-Analyst",
        },
        {
            "username": "e474e7a9-71ca-449d-833c-8a6e094dd117",
            "first_name": "Rebecca-Analyst",
            "last_name": "Hsieh-Analyst",
        },
        {
            "username": "5dc6c9a6-61d9-42b4-ba54-4beff28bac3c",
            "first_name": "David-Analyst",
            "last_name": "Kennedy-Analyst",
        },
        {
            "username": "0eb6f326-a3d4-410f-a521-aa4c1fad4e47",
            "first_name": "Gaby-Analyst",
            "last_name": "DiSarli-Analyst",
            "email": "gaby@truss.works",
        },
        {
            "username": "cfe7c2fc-e24a-480e-8b78-28645a1459b3",
            "first_name": "Nicolle-Analyst",
            "last_name": "LeClair-Analyst",
            "email": "nicolle.leclair@ecstech.com",
        },
    ]
    
    def load_users(cls, users, group_name):
        logger.info(f"Going to load {len(users)} users in group {group_name}")
        for user_data in users:
            try:
                user, _ = User.objects.get_or_create(username=user_data["username"])
                user.is_superuser = False
                user.first_name = user_data["first_name"]
                user.last_name = user_data["last_name"]
                if "email" in user_data:
                    user.email = user_data["email"]
                user.is_staff = True
                user.is_active = True
                group = UserGroup.objects.get(name=group_name)
                user.groups.add(group)
                user.save()
                logger.debug(f"User object created for {user_data['first_name']}")
            except Exception as e:
                logger.warning(e)
        logger.info(f"All users in group {group_name} loaded.")

    @classmethod
    def load(cls):
        cls.load_users(cls, cls.ADMINS, "full_access_group")
        cls.load_users(cls, cls.STAFF, "cisa_analysts_group")

