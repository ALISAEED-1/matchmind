"""Deterministic card templates in English, Urdu and Arabic.

Used in two situations:

* **routing**: low-importance moments (substitutions, milestones, yellow cards)
  go straight to a template, so LLM time is spent where it matters;
* **recovery**: when every model in the chain fails, the orchestrator still
  publishes a correct card from these templates (marked `fallback_used`).

Every number comes from `MomentFacts.fields`, so template cards are always
accurate. Player and club names stay in Latin letters in every language.
"""

from __future__ import annotations

from matchmind.cards import Audience, CardType, Language
from matchmind.stats import MomentKind

# kind -> language -> audience -> (title, body, why_it_matters)
Template = tuple[str, str, str]
TEMPLATES: dict[str, dict[Language, dict[Audience, Template]]] = {
    "goal": {
        Language.EN: {
            Audience.FAN: (
                "GOAL! {player}",
                "{player} scores for {team} at {minute}. {score}.",
                "A goal changes everything: now {opp} have to respond.",
            ),
            Audience.ANALYST: (
                "Goal: {player}, {xg} xG",
                "{team} score from a {xg} xG chance at {minute}. {score}.",
                "Converting chances of this quality decides tight matches.",
            ),
        },
        Language.UR: {
            Audience.FAN: (
                "گول! {player}",
                "{player} نے {minute} پر {team} کے لیے گول کر دیا۔ {score}",
                "اس گول نے سب کچھ بدل دیا، اب {opp} کو جواب دینا ہوگا۔",
            ),
            Audience.ANALYST: (
                "گول: {player}، {xg} xG",
                "{team} نے {minute} پر {xg} xG والے موقع کو گول میں بدلا۔ {score}",
                "ایسے مواقع کو گول میں بدلنا کانٹے دار مقابلوں کا فیصلہ کرتا ہے۔",
            ),
        },
        Language.AR: {
            Audience.FAN: (
                "هدف! {player}",
                "{player} يسجل لفريق {team} عند الدقيقة {minute}. {score}",
                "هدف يغير كل شيء، وعلى {opp} أن يرد الآن.",
            ),
            Audience.ANALYST: (
                "هدف: {player}، {xg} xG",
                "{team} يسجل من فرصة قيمتها {xg} xG عند الدقيقة {minute}. {score}",
                "استغلال فرص بهذه الجودة يحسم المباريات المتقاربة.",
            ),
        },
    },
    "big_chance": {
        Language.EN: {
            Audience.FAN: (
                "So close!",
                "{player} goes close for {team} at {minute}.",
                "{team} are getting into dangerous positions.",
            ),
            Audience.ANALYST: (
                "Big chance: {xg} xG",
                "{player} ({team}) shoots from {distance} m: {outcome}. Chance worth {xg} xG.",
                "High-quality chances like this usually end up in the net.",
            ),
        },
        Language.UR: {
            Audience.FAN: (
                "بال بال بچ گئے!",
                "{minute} پر {player} گول کے بہت قریب پہنچ گئے۔",
                "{team} خطرناک جگہوں تک پہنچ رہے ہیں۔",
            ),
            Audience.ANALYST: (
                "بڑا موقع: {xg} xG",
                "{player} نے {distance} میٹر سے شاٹ لگایا۔ اس موقع کی قدر {xg} xG تھی۔",
                "اتنے اچھے مواقع عام طور پر گول میں بدل جاتے ہیں۔",
            ),
        },
        Language.AR: {
            Audience.FAN: (
                "فرصة ضائعة!",
                "{player} يقترب من التسجيل لفريق {team} عند الدقيقة {minute}.",
                "{team} يصل إلى مناطق خطيرة.",
            ),
            Audience.ANALYST: (
                "فرصة كبيرة: {xg} xG",
                "تسديدة من {player} من مسافة {distance} م، وقيمة الفرصة {xg} xG.",
                "الفرص بهذه الجودة تنتهي عادة في الشباك.",
            ),
        },
    },
    "red_card": {
        Language.EN: {
            Audience.FAN: (
                "Red card!",
                "{player} is sent off at {minute}. {team} are down to 10 men.",
                "Playing a man down, {team} will struggle to keep the ball.",
            ),
            Audience.ANALYST: (
                "Red card: {player}",
                "{team} lose {player} at {minute} and continue with 10 players.",
                "Expect {opp} to dominate possession and push {team} deeper.",
            ),
        },
        Language.UR: {
            Audience.FAN: (
                "ریڈ کارڈ!",
                "{player} کو {minute} پر باہر بھیج دیا گیا۔ {team} اب 10 کھلاڑیوں کے ساتھ ہیں۔",
                "ایک کھلاڑی کم ہونے سے {team} کے لیے گیند رکھنا مشکل ہوگا۔",
            ),
            Audience.ANALYST: (
                "ریڈ کارڈ: {player}",
                "{minute} پر {team} نے {player} کو کھو دیا اور اب 10 کھلاڑی ہیں۔",
                "توقع ہے کہ {opp} گیند پر قبضہ بڑھائیں گے۔",
            ),
        },
        Language.AR: {
            Audience.FAN: (
                "بطاقة حمراء!",
                "طرد {player} عند الدقيقة {minute}، و{team} يكمل بعشرة لاعبين.",
                "النقص العددي سيصعّب على {team} الاحتفاظ بالكرة.",
            ),
            Audience.ANALYST: (
                "بطاقة حمراء: {player}",
                "{team} يفقد {player} عند الدقيقة {minute} ويواصل بعشرة لاعبين.",
                "من المتوقع أن يستحوذ {opp} على الكرة ويدفع {team} إلى الخلف.",
            ),
        },
    },
    "yellow_card": {
        Language.EN: {
            Audience.FAN: ("Yellow card", "{player} ({team}) is booked at {minute}.", ""),
            Audience.ANALYST: ("Booking: {player}", "{player} ({team}) booked at {minute}.", ""),
        },
        Language.UR: {
            Audience.FAN: ("یلو کارڈ", "{minute} پر {player} کو یلو کارڈ دکھایا گیا۔", ""),
            Audience.ANALYST: (
                "یلو کارڈ: {player}",
                "{minute} پر {player} ({team}) کو وارننگ۔",
                "",
            ),
        },
        Language.AR: {
            Audience.FAN: ("بطاقة صفراء", "إنذار لـ{player} عند الدقيقة {minute}.", ""),
            Audience.ANALYST: (
                "إنذار: {player}",
                "إنذار لـ{player} ({team}) عند الدقيقة {minute}.",
                "",
            ),
        },
    },
    "momentum_shift": {
        Language.EN: {
            Audience.FAN: (
                "{team} take over",
                "The game has swung towards {team}.",
                "Teams on top like this often find a goal soon.",
            ),
            Audience.ANALYST: (
                "Momentum shift: {team}",
                "Momentum moved from {from} to {to} in 5 minutes (-1 {away}, +1 {home}).",
                "{team} are now creating more danger than {opp}.",
            ),
        },
        Language.UR: {
            Audience.FAN: (
                "{team} چھا گئے",
                "میچ کا پلڑا اب {team} کی طرف جھک گیا ہے۔",
                "ایسے لمحوں میں اکثر گول آ جاتا ہے۔",
            ),
            Audience.ANALYST: (
                "مومینٹم میں تبدیلی: {team}",
                "پانچ منٹ میں مومینٹم {from} سے {to} ہو گیا۔",
                "{team} اب {opp} سے زیادہ خطرہ پیدا کر رہے ہیں۔",
            ),
        },
        Language.AR: {
            Audience.FAN: (
                "{team} يسيطر",
                "انقلبت المباراة لصالح {team}.",
                "الفريق المسيطر بهذا الشكل يسجل غالبا قريبا.",
            ),
            Audience.ANALYST: (
                "تحول في الزخم: {team}",
                "تحرك الزخم من {from} إلى {to} خلال خمس دقائق.",
                "{team} يصنع الآن خطورة أكبر من {opp}.",
            ),
        },
    },
    "pressure_surge": {
        Language.EN: {
            Audience.FAN: (
                "{team} turn up the heat",
                "{team} are pressing high and hard.",
                "Pressure like this forces mistakes.",
            ),
            Audience.ANALYST: (
                "Pressure surge: {team}",
                "{team}'s pressure index is {pressure}, up from {prev} in the previous 10 minutes.",
                "{opp} are being squeezed and will struggle to build from the back.",
            ),
        },
        Language.UR: {
            Audience.FAN: (
                "{team} کا زبردست دباؤ",
                "{team} آگے بڑھ کر بھرپور دباؤ ڈال رہے ہیں۔",
                "ایسا دباؤ غلطیاں کرواتا ہے۔",
            ),
            Audience.ANALYST: (
                "دباؤ میں اضافہ: {team}",
                "{team} کا پریشر انڈیکس {pressure} ہے، پچھلے 10 منٹ میں {prev} تھا۔",
                "{opp} کے لیے پیچھے سے کھیل بنانا مشکل ہو گیا ہے۔",
            ),
        },
        Language.AR: {
            Audience.FAN: (
                "{team} يرفع الضغط",
                "{team} يضغط عاليا وبقوة.",
                "ضغط كهذا يجبر الخصم على الأخطاء.",
            ),
            Audience.ANALYST: (
                "تصاعد الضغط: {team}",
                "مؤشر ضغط {team} بلغ {pressure} بعد أن كان {prev} في الدقائق العشر السابقة.",
                "{opp} يعاني لبناء اللعب من الخلف.",
            ),
        },
    },
    "chaos_spell": {
        Language.EN: {
            Audience.FAN: (
                "End to end!",
                "The game has turned wild: the ball keeps changing hands.",
                "Anything can happen in spells like this.",
            ),
            Audience.ANALYST: (
                "Chaos spell: {chaos}",
                "{turnovers} turnovers per minute and only {seq} passes per possession.",
                "Neither side has control; transitions now decide the game.",
            ),
        },
        Language.UR: {
            Audience.FAN: (
                "زبردست اتار چڑھاؤ!",
                "میچ بے قابو ہو گیا ہے، گیند بار بار ہاتھ بدل رہی ہے۔",
                "ایسے لمحوں میں کچھ بھی ہو سکتا ہے۔",
            ),
            Audience.ANALYST: (
                "بے ترتیبی کا دور: {chaos}",
                "فی منٹ {turnovers} بار گیند ہاتھ سے گئی اور ہر قبضے میں صرف {seq} پاس۔",
                "کسی ٹیم کا کنٹرول نہیں، اب جوابی حملے فیصلہ کریں گے۔",
            ),
        },
        Language.AR: {
            Audience.FAN: (
                "مباراة مفتوحة!",
                "المباراة أصبحت جنونية والكرة تتنقل بين الفريقين باستمرار.",
                "كل شيء ممكن في مثل هذه الفترات.",
            ),
            Audience.ANALYST: (
                "فترة فوضى: {chaos}",
                "{turnovers} فقدان للكرة في الدقيقة و{seq} تمريرة فقط في كل استحواذ.",
                "لا سيطرة لأي فريق، والتحولات ستحسم اللقاء.",
            ),
        },
    },
    "rocket_shot": {
        Language.EN: {
            Audience.FAN: ("What a strike!", "{player} unleashes a {speed} km/h shot.", ""),
            Audience.ANALYST: ("Shot speed: {speed} km/h", "{player} ({team}): {outcome}.", ""),
        },
        Language.UR: {
            Audience.FAN: (
                "زوردار شاٹ!",
                "{player} کا {speed} کلومیٹر فی گھنٹہ کی رفتار سے شاٹ۔",
                "",
            ),
            Audience.ANALYST: ("شاٹ کی رفتار: {speed} km/h", "{player} ({team}) کا شاٹ۔", ""),
        },
        Language.AR: {
            Audience.FAN: ("تسديدة صاروخية!", "{player} يسدد بسرعة {speed} كم/س.", ""),
            Audience.ANALYST: ("سرعة التسديدة: {speed} km/h", "تسديدة {player} ({team}).", ""),
        },
    },
    "elite_pass": {
        Language.EN: {
            Audience.FAN: ("What a pass!", "{player} threads a brilliant ball through.", ""),
            Audience.ANALYST: (
                "Elite pass: {difficulty}/100",
                "{player} completes a {distance} m pass rated {difficulty}/100 for difficulty.",
                "",
            ),
        },
        Language.UR: {
            Audience.FAN: ("کمال کا پاس!", "{player} کا شاندار پاس۔", ""),
            Audience.ANALYST: (
                "بہترین پاس: {difficulty}/100",
                "{player} کا {distance} میٹر لمبا پاس، مشکل درجہ {difficulty}/100۔",
                "",
            ),
        },
        Language.AR: {
            Audience.FAN: ("تمريرة رائعة!", "{player} يمرر كرة متقنة.", ""),
            Audience.ANALYST: (
                "تمريرة نخبوية: {difficulty}/100",
                "تمريرة من {player} لمسافة {distance} م بدرجة صعوبة {difficulty}/100.",
                "",
            ),
        },
    },
    "top_speed": {
        Language.EN: {
            Audience.FAN: ("Full throttle!", "{player} flies forward at {speed} km/h.", ""),
            Audience.ANALYST: (
                "Top speed: {speed} km/h",
                "{player} ({team}) carry at {speed} km/h.",
                "",
            ),
        },
        Language.UR: {
            Audience.FAN: (
                "برق رفتاری!",
                "{player} {speed} کلومیٹر فی گھنٹہ کی رفتار سے دوڑے۔",
                "",
            ),
            Audience.ANALYST: ("تیز ترین رفتار: {speed} km/h", "{player} ({team}) کی دوڑ۔", ""),
        },
        Language.AR: {
            Audience.FAN: ("انطلاقة صاروخية!", "{player} ينطلق بسرعة {speed} كم/س.", ""),
            Audience.ANALYST: ("السرعة القصوى: {speed} km/h", "انطلاقة {player} ({team}).", ""),
        },
    },
    "pass_milestone": {
        Language.EN: {
            Audience.FAN: ("{player}: {passes} passes", "{player} keeps {team} ticking.", ""),
            Audience.ANALYST: (
                "{passes} completed passes",
                "{player} ({team}) reaches {passes}.",
                "",
            ),
        },
        Language.UR: {
            Audience.FAN: ("{player}: {passes} پاس", "{player} {team} کا کھیل چلا رہے ہیں۔", ""),
            Audience.ANALYST: ("{passes} مکمل پاس", "{player} ({team}) کے {passes} پاس مکمل۔", ""),
        },
        Language.AR: {
            Audience.FAN: ("{player}: {passes} تمريرة", "{player} يدير لعب {team}.", ""),
            Audience.ANALYST: ("{passes} تمريرة ناجحة", "{player} ({team}) يصل إلى {passes}.", ""),
        },
    },
    "shot_milestone": {
        Language.EN: {
            Audience.FAN: ("{team}: {shots} shots", "{team} keep testing the goalkeeper.", ""),
            Audience.ANALYST: (
                "{team}: {shots} shots",
                "{team} reach {shots} shots at {minute}.",
                "",
            ),
        },
        Language.UR: {
            Audience.FAN: ("{team}: {shots} شاٹس", "{team} مسلسل گول پر حملے کر رہے ہیں۔", ""),
            Audience.ANALYST: ("{team}: {shots} شاٹس", "{minute} تک {team} کے {shots} شاٹس۔", ""),
        },
        Language.AR: {
            Audience.FAN: ("{team}: {shots} تسديدات", "{team} يواصل اختبار الحارس.", ""),
            Audience.ANALYST: ("{team}: {shots} تسديدات", "{team} يصل إلى {shots} تسديدات.", ""),
        },
    },
    "substitution": {
        Language.EN: {
            Audience.FAN: ("Substitution", "{on_player} comes on for {player} ({team}).", ""),
            Audience.ANALYST: ("Change: {team}", "{player} off, {on_player} on at {minute}.", ""),
        },
        Language.UR: {
            Audience.FAN: ("تبدیلی", "{team}: {player} کی جگہ {on_player} میدان میں۔", ""),
            Audience.ANALYST: (
                "تبدیلی: {team}",
                "{minute} پر {player} باہر، {on_player} اندر۔",
                "",
            ),
        },
        Language.AR: {
            Audience.FAN: ("تبديل", "{team}: دخول {on_player} بدلا من {player}.", ""),
            Audience.ANALYST: ("تبديل: {team}", "خروج {player} ودخول {on_player}.", ""),
        },
    },
    "half_time": {
        Language.EN: {
            Audience.FAN: ("Half time", "{score}.", ""),
            Audience.ANALYST: ("Half time", "{score}.", ""),
        },
        Language.UR: {
            Audience.FAN: ("ہاف ٹائم", "{score}", ""),
            Audience.ANALYST: ("ہاف ٹائم", "{score}", ""),
        },
        Language.AR: {
            Audience.FAN: ("نهاية الشوط الأول", "{score}", ""),
            Audience.ANALYST: ("نهاية الشوط الأول", "{score}", ""),
        },
    },
    "full_time": {
        Language.EN: {
            Audience.FAN: ("Full time", "{score}.", ""),
            Audience.ANALYST: ("Full time", "{score}.", ""),
        },
        Language.UR: {
            Audience.FAN: ("میچ ختم", "{score}", ""),
            Audience.ANALYST: ("میچ ختم", "{score}", ""),
        },
        Language.AR: {
            Audience.FAN: ("نهاية المباراة", "{score}", ""),
            Audience.ANALYST: ("نهاية المباراة", "{score}", ""),
        },
    },
}

COMMENTARY_TEMPLATES: dict[Language, str] = {
    Language.EN: "{minute}: {title}.",
    Language.UR: "{minute}: {title}",
    Language.AR: "{minute}: {title}",
}

CARD_TYPE: dict[MomentKind, CardType] = {
    MomentKind.GOAL: CardType.INSIGHT,
    MomentKind.BIG_CHANCE: CardType.INSIGHT,
    MomentKind.RED_CARD: CardType.INSIGHT,
    MomentKind.MOMENTUM_SHIFT: CardType.INSIGHT,
    MomentKind.PRESSURE_SURGE: CardType.INSIGHT,
    MomentKind.CHAOS_SPELL: CardType.INSIGHT,
    MomentKind.ROCKET_SHOT: CardType.STAT,
    MomentKind.ELITE_PASS: CardType.STAT,
    MomentKind.TOP_SPEED: CardType.STAT,
    MomentKind.YELLOW_CARD: CardType.STAT,
    MomentKind.SUBSTITUTION: CardType.STAT,
    MomentKind.HALF_TIME: CardType.STAT,
    MomentKind.PASS_MILESTONE: CardType.MILESTONE,
    MomentKind.SHOT_MILESTONE: CardType.MILESTONE,
    MomentKind.FULL_TIME: CardType.RECAP,
}


class _Blank(dict):
    def __missing__(self, key: str) -> str:
        return ""


def render(
    kind: MomentKind, language: Language, audience: Audience, fields: dict[str, str]
) -> tuple[str, str, str | None]:
    """(title, body, why_it_matters) for a moment from the deterministic templates."""
    per_audience = TEMPLATES[kind.value][language]
    title, body, why = per_audience.get(audience) or per_audience[Audience.FAN]
    values = _Blank(fields)
    return title.format_map(values), body.format_map(values), (why.format_map(values) or None)
