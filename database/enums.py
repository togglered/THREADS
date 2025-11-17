from enum import Enum as PyEnum, IntEnum


class DatabaseEnums:
    class DayOfWeek(IntEnum):
        monday = 0
        tuesday = 1
        wednesday = 2
        thursday = 3
        friday = 4
        saturday = 5
        sunday = 6

        @property
        def label(self):
            labels = {
                DatabaseEnums.DayOfWeek.monday: "Понедельник",
                DatabaseEnums.DayOfWeek.tuesday: "Вторник",
                DatabaseEnums.DayOfWeek.wednesday: "Среда",
                DatabaseEnums.DayOfWeek.thursday: "Четверг",
                DatabaseEnums.DayOfWeek.friday: "Пятница",
                DatabaseEnums.DayOfWeek.saturday: "Суббота",
                DatabaseEnums.DayOfWeek.sunday: "Воскресенье",
            }
            return labels[self]


    class Sex(PyEnum):
        male = 'муж.'
        female = 'жен.'
        other = 'иной'


    class CommunicationStyle(PyEnum):
        friendly = 'дружелюбный'
        sarcastic = 'саркастичный'
        aggressive = 'агрессивный'
        naive = 'наивный'
        cynical = 'циничный'
        professional = 'деловой'


    class EngagementLevel(PyEnum):
        neutral = 'нейтральный'
        moderate = 'умеренный'
        peak = 'максимальный'


    class EngagementCategories(PyEnum):
        relationships = 'отношения'
        social_injustice = 'социальное неравенство'
        personal_dramas = 'персональная драма'
        humor = 'юмор'
        politics = 'политика'
        religion = 'религия'

        @property
        def is_special(self):
            return self in (
                DatabaseEnums.EngagementCategories.politics,
                DatabaseEnums.EngagementCategories.religion
            )
