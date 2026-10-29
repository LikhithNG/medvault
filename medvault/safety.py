#!/usr/bin/env python3
"""The three checks that decide what the Companion's model never gets to say.

  is_emergency  a question describing an emergency gets the fixed 911 answer (ask.triage)
  is_decision   a question asking for a dose decision gets ask.decision()'s answer
  directs       a model answer that tells somebody to change a dose is replaced

They were short keyword lists with a few unit tests each, and nobody knew what they missed.
tools/safety_eval.py measured them against 570 phrasings a separate writer labelled
without seeing them (bench/safety_cases.json): before this module, the emergency check
caught a quarter of the emergencies, the dose check a fifth of the dose questions, and the
answer check under a tenth of the dose instructions. They were rewritten against the tuning
half of that bench only; the held-out half, never looked at, is the number to quote - see
the README. They are still patterns. The held-out misses are where to look next.

Each check errs on one side on purpose. Missing an emergency or a dose instruction is
worse than a false alarm, which costs one fixed answer the person can rephrase past.
"""
import re


def plain(text):
    """Lowercase, single-spaced, and with a phone's curly apostrophe made straight - iOS
    types "can’t breathe", and every pattern here is written with "'"."""
    return " ".join((text or "").lower().replace("\u2019", "'").split())


def plain_keep_lines(text):
    """plain(), but with the line breaks kept: an answer's lines are separate sentences."""
    return "\n".join(plain(line) for line in (text or "").splitlines())


# ---- emergencies ------------------------------------------------------------------------

# Asked in the middle of something happening, the right output is six words and a phone
# number, not a paragraph. Patterns rather than keywords, because nobody types the textbook
# phrase: the measured misses were "her face looks lopsided", "he's not waking up", "I just
# took a whole bottle", "feels like an elephant is sitting on my chest".
EMERGENCY = tuple(re.compile(p) for p in (
    # the heart
    r"chest('s)?\b.{0,30}(pain|tight|hurt|ach|pressure|heav|squeez|crush)",
    r"(pain|pressure|tightness|crushing|weight)\s+(in|on|across)\s+(my|his|her|the)\s+chest",
    r"(elephant|weight|something\s+heavy)\s+(is\s+)?(sitting|sat|pressing|on)\s+(on\s+)?"
    r"(my|his|her)\s+chest",
    r"(gone|turned|going|looks?|looking)\s+(grey|gray|ashen)|can'?t\s+stand\s+up",
    r"squeez\w*\s+(my|his|her)\s+(heart|chest)",
    r"(having|signs\s+of|think\s+\w+\s+having)\s+a?\s*(stroke|seizure|heart\s+attack)",
    r"stroke\s+symptoms|heart\s+attack\s+symptoms",
    # breathing, choking, colour
    r"can'?t\s+breath|cannot\s+breath|not\s+able\s+to\s+breath|can\s+barely\s+(breath|talk"
    r"|speak|get\s+air)|through\s+a\s+straw|only\s+get\s+(out\s+)?(a\s+)?(couple|few)\s+(of\s+)?"
    r"words|(breathing|breathless|out\s+of\s+breath).{0,100}(getting\s+worse|worse\s+by)",
    r"wheez\w*\s+(badly|really\s+bad|so\s+bad)|sucking\s+in\s+(under|between)",
    r"(inhaler|ventolin|albuterol|puffer)('s)?\s+(is\s+)?(isn'?t|not|doing\s+nothing)\s*"
    r"(touching|helping|working)?",
    r"can'?t\s+(cough|breathe)\s+or\s+(speak|talk)|(gone|went)\s+down\s+the\s+wrong\s+way"
    r"|\blodged\b|stuck\s+in\s+(my|his|her)\s+throat",
    r"(trouble|difficulty|struggling|hard)\s+\w*\s*breath",
    r"short(ness)?\s+of\s+breath",
    r"(is|are|'s|'re|i'?m|i\s+am)\s+not\s+breathing|(isn'?t|aren'?t)\s+breathing"
    r"|stopped\s+breathing",
    r"(is|are|'s|'re|i'?m|i\s+am)\s+choking",
    r"gasping",
    r"(turning|turned|gone|going|went)\s+blue|lips\s+\w*\s*blue|blue\s+lips",
    r"(having|in\s+the\s+middle\s+of)\s+an?\s+(bad\s+|severe\s+)?asthma\s+attack",
    # a severe allergic reaction
    r"anaphyla",
    r"throat('s)?\s+(\w+\s+)?(clos|tight|swell|swoll)|voice.{0,25}tight",
    r"tongue\s+\w*\s*swell|swollen\s+tongue|tongue\s+(feels\s+)?(too\s+big|thick)",
    r"(lips|eyes|face|tongue|mouth)('s)?\s+(and\s+\w+\s+)?.{0,20}(swell|swoll|swel|puff)",
    # bleeding
    r"(severe|heavy|heavily|badly|won'?t\s+stop|can'?t\s+stop)\s+\w*\s*bleed",
    r"bleeding\s+(heavily|badly|a\s+lot)",
    r"(coughing|throwing|vomiting|spitting|puking)\s+(up\s+)?(\w+\s+){0,2}blood",
    r"(vomit|throwing\s+up|puking|being\s+sick).{0,30}blood",
    r"blood\s+(is\s+)?(gushing|pouring|spurting|everywhere)|gushing\s+blood",
    r"(nosebleed|bleeding).{0,30}(an\s+hour|hours|soak|won'?t\s+stop|faint)",
    r"soak\w*\s+through|pumping\s+out|(pressing|pressure).{0,30}(won'?t|wont)\s+stop",
    # consciousness, seizures, a head injury, low sugar
    r"unconscious|passed\s+out|blacked\s+out|collapsed|unresponsive",
    r"(can'?t|cannot|couldn'?t)\s+(wake|rouse)\s+(him|her|them|my|\w+\s+up)",
    r"(not|isn'?t|won'?t)\s+(waking|wake|woken)|(hard|difficult|impossible)\s+to\s+wake",
    r"(isn'?t|not|stopped)\s+respond",
    r"(is|are|'s|gone|went)\s+limp",
    r"(had|having)\s+a\s+(fit|seizure)|still\s+(twitching|jerking|seizing|shaking)"
    r"|(jerking|twitching|convulsing|shaking)\s+all\s+over|eyes\s+(rolled|rolling)\s+back"
    r"|convuls|foaming\s+at\s+the\s+mouth|(jerking|twitching|fitting|seizing)\s+(and|on)\b",
    r"hit\s+(his|her|my|their)\s+head.{0,60}(confus|throw\w*\s+up|vomit|drowsy|not\s+mak)",
    r"(isn'?t|not)\s+making\s+(any\s+)?sense|(shaky|sweaty|clammy).{0,30}confus",
    # a stroke
    r"slurr\w*\s+speech",
    r"face\s+(\w+\s+){0,2}(droop|lopsided|uneven|crooked|sagg)",
    r"(mouth|lip|face)\b.{0,30}(droop|deviat)",
    r"(can'?t|cannot|unable\s+to)\s+(lift|raise|move|feel)\s+(my|his|her|the)\s+(\w+\s+)?"
    r"(arm|leg|side)",
    r"(leg|arm|hand)\s+(won'?t|wont|doesn'?t|isn'?t)\s+(work|move|hold|grip|lift)",
    r"(left|right|one)\s+side\b.{0,30}(heavy|numb|weak|dead|droop|weird|tingl)",
    r"(heavy|numb|weak|dead|droop|weird|tingl)\w*\s+(on\s+)?(the\s+)?(left|right|one)\s+side",
    r"(arm|leg)('s|\s+has|\s+is)?\s+(gone|went|feels|just\s+went)\s+(heavy|numb|dead|weak)",
    r"(lost|losing)\s+(the\s+)?(power\s+of\s+)?speech|words\s+(are\s+)?(coming|come)\s+out"
    r"\s+(wrong|jumbled|garbled)|speech\s+(is\s+)?(slurred|garbled|jumbled)"
    r"|can'?t\s+(speak|talk)\s+(properly|clearly|at\s+all)",
    r"sudden(ly)?\s+(\w+\s+)?(weakness|numbness|numb|weak)\b",
    r"worst\s+headache",
    r"can'?t\s+see\s+(properly\s+|clearly\s+)?(out\s+of|in|with)\s+(one|my|his|her)\s+eye",
    # too much of a medicine
    r"overdose|took\s+(too|to)\s+many|swallowed\s+the\s+whole",
    r"(took|taken|swallowed|ate|eaten|drank|downed|injected|got\s+into)\s+(\w+\s+){0,2}(whole"
    r"|entire|full|rest\s+of|bunch|handful|lot\s+of|alot|too\s+much|too\s+many|way\s+too)",
    r"swallowed\s+(a|an|one\s+of\s+the)\s+(\w+\s+)?(batter|magnet)"
    r"|(packet|bottle|box)('s|\s+is)\s+empty|empty\s+(packet|bottle)",
    r"(swallowed|ate|got\s+into)\s+(\w+\s+){0,2}(some|all)\s+of",
    r"(swallowed|ate|drank|downed)\s+all\s+(my|her|his|the|their)",
    r"took\s+.{0,40}on\s+purpose",
    # harm to oneself
    r"suicid|kill\s+myself|end\s+my\s+life|harm\s+myself|hurt(ing)?\s+myself|want\s+to\s+die"
    r"|wanna\s+die",
    r"cut\s+(myself|(my|her|his|their)\s+wrists?)",
    r"thoughts\s+of\s+(hurting|killing|ending|harming)",
    r"don'?t\s+want\s+to\s+(be\s+here|live|be\s+alive|wake\s+up)|(tablets|pills)\s+lined\s+up"
    r"|thinking\s+about\s+(driving|crashing|jumping|ending|killing)",
))

# The same words in a question about a page, or about the past - "what does my discharge
# note say about chest pain?", "my brother overdosed two years ago", "what are the warning
# signs of a stroke" - are not an emergency, and every one of those got the 911 answer.
# Present-tense words override it: a document question that says "now" or "is swelling"
# is answered as an emergency, because missing one costs more than a false alarm.
ABOUT_A_PAGE_OR_THE_PAST = re.compile(
    r"\b(note|notes|letter|records?|report|leaflet|label|box|chart|summary|papers|history)"
    r"\s+(say|says|said|mention|mentions|states?|show|shows)\b"
    r"|\b(in|on|from)\s+(my|the|his|her)\s+(\w+\s+){0,3}(note|notes|letter|records?|report"
    r"|leaflet|label|box|chart|summary|papers|file)\b"
    r"|\b(years?|months?|weeks?)\s+ago\b|\blast\s+(year|month|summer|winter|spring|fall)\b"
    r"|\b(in|from|since|back\s+in)\s+(19|20)\d\d\b"
    r"|\bwhen\s+(i|he|she)\s+was\s+(hospitali[sz]ed|admitted|little|a\s+(kid|child|baby))\b"
    r"|\bwarning\s+signs?\b|\b(what|which)\s+(are|is)\s+(the\s+)?(\w+\s+)?(signs|symptoms)"
    r"\s+of\b"
    r"|\bside[\s-]?eff?ects?\b"
    r"|\bwhen\s+(i|you|he|she|they)\s+(get|feel)\b"
    r"|\b(in|last|back\s+in)\s+(january|february|march|april|may|june|july|august|september"
    r"|october|november|december)\b|\b(they|he|she|the\s+doctors?|the\s+nurse)\s+(said|told)\b"
    r"|\b(main|common|usual|typical)\s+(sign|symptom)s?\b|\bhow\s+do\s+(they|doctors|you)\s+treat\b"
    r"|\bwhat\s+happens\s+(in|to|when|during)\b")
HAPPENING_NOW = re.compile(
    r"\b(right\s+now|now|currently|at\s+the\s+moment|ambulance|911|still|keeps?)\b"
    r"|\bjust\s+(now|took|taken|swallowed|ate|drank|had|started|happened|came\s+on|went"
    r"|collapsed|fell)\b"
    r"|^help\b|\bhelp\s*!|\b(please|pls|someone)\s+help\b"
    # "my lips are swelling", "she's jerking" - present tense with somebody doing it. Not a
    # question opening with "is": "Is crushing chest pain the main sign...?" asks about a sign.
    r"|\w('s|'re)\s+\w+ing\b|(?<=\w\s)(is|are|am)\s+\w+ing\b|\bi'?m\s+\w+ing\b"
    r"|\bi'?ve\s+been\s+having\b")


def is_emergency(question):
    q = plain(question)
    if not any(p.search(q) for p in EMERGENCY):
        return False
    return not (ABOUT_A_PAGE_OR_THE_PAST.search(q) and not HAPPENING_NOW.search(q))


# ---- dose decisions ---------------------------------------------------------------------

# A decision about a dose belongs to the person who prescribed it. The app's job is to put
# what the record actually says in front of them, not to answer instead of the prescriber.
# The list of exact phrases it used to be caught one question in five; people ask "do I
# really have to finish all the antibiotics" and "can I split my 50 mg to make 25".
_WHO = (r"(i|we|he|she|they|my\s+\w+|mom|mum|mother|dad|father|son|daughter|baby|child|kid"
        r"|husband|wife|partner|grandma|grandpa|grandad|granddad|toddler)")
_MODAL = r"(can|could|should|shall|may|must|would|will)"
_SOFT = r"(\s+(still|really|just|safely|now|also|even|then|maybe|actually|be))*"
_ACT = (r"(take|taking|tkae|stop+|skip|quit|pause|hold|restart|resume|start|split|cut|crush"
        r"|chew|open|sprinkle|mix|use|double|halve|increase|decrease|reduce|lower|wean"
        r"|come\s+off|snap|grind|break|dissolve|carry\s+on"
        r"|go\s+back\s+on|get\s+back\s+on|go\s+off|keep|stay\s+on|continue|give|switch|swap"
        r"|change|drink|finish|combine|have\s+(a|another)\s+(drink|beer|glass|wine))")
DECISION = tuple(re.compile(p) for p in (
    # "can I take", "should my mom stop", "should she just restart"
    rf"\b{_MODAL}\s+{_WHO}{_SOFT}\s+{_ACT}\b",
    # "do I really have to finish", "do I take an extra" - but not "what do I take", which
    # asks what the records say
    rf"(?<!what )(?<!which )(?<!when )\b(do|does)\s+{_WHO}{_SOFT}\s+((have|need|got)\s+to\s+)?"
    rf"{_ACT}\b",
    # "tell me if I can take", "is apixaban something I can stay on"
    rf"\b(if|whether)\s+{_WHO}\s+{_MODAL}{_SOFT}\s+{_ACT}\b",
    rf"\b{_WHO}\s+can{_SOFT}\s+(stay\s+on|keep\s+(taking|using))\b",
    # "is it ok to cut", "would it be ok to skip", "ok to take 3 advil"
    rf"\b(is|would|will)\s+it\s+(be\s+)?(ok|okay|alright|all\s+right|fine|safe|a\s+problem"
    rf"|bad|a\s+bad\s+idea|wise)\s+(for\s+\w+(\s+\w+)?\s+)?(to\s+{_ACT}|if)\b",
    rf"\b(ok|okay|alright|fine|safe)\s+(for\s+(me|my\s+\w+|him|her)\s+)?to\s+{_ACT}\b",
    # "are these capsules ok for me", "is tylenol a bad idea for me"
    r"\b(is|are|be|was)\s+(\w+\s+){0,4}?(ok|okay|safe|fine|a\s+problem|a\s+bad\s+idea|bad"
    r"|dangerous)\s+for\s+(me|him|her|my\s+\w+)\b",
    rf"\bbe\s+a\s+problem\s+if\s+{_WHO}\s+(take|use|stop|skip)",
    # "...instead of 8am, is that ok?", "would that work for me?", "at the same time, problem?"
    r"\b(is|would)\s+(that|this)\s+(be\s+)?(ok|okay|alright|fine|safe|a\s+problem|work)\b",
    r"\bbe\s+(ok|okay|alright|fine)\s+for\s+(me|my)\b",
    r",\s*problem\s*\?",
    # "thinking of stopping my statin", "I'm going to try one every other day", "planning a
    # drug holiday" - a plan stated, which is a question for the prescriber all the same
    r"\b(thinking\s+(of|about)|planning\s+(to|on)|going\s+to|gonna|was\s+going\s+to"
    r"|wondering\s+(whether|if)\s+to|considering|i'?ll)\s+(\w+\s+){0,2}(stop|cut|drop|switch"
    r"|skip|halve|double|try|stay\s+on|pause|quit|reduce|come\s+off|wean|ditch)",
    r"\bdrug\s+holiday\b|\bdouble\s+up\b|\bor\s+(just\s+)?(leave|skip)\s+it\b",
    # "would you skip your Eliquis", "when do I stop my xarelto"
    r"\bwould\s+you\s+(\w+\s+){0,2}(take|skip|stop|start|double|halve|have)\b",
    rf"\bwhen\s+(do|should|can)\s+{_WHO}\s+(stop|start|restart|resume|go\s+back|come\s+off"
    rf"|quit|pause)\b",
    # "can she have Advil", "can I have another 2 paracetamol", "I can have a few frothies"
    rf"\b(can|could|may)\s+(she|he|they|my\s+\w+|baby)\s+(have|hav)\b",
    rf"\b{_WHO}\s+(can|could|may)?\s*(have|hav)\s+(another|an\s+extra|extra|\d+|a\s+few"
    rf"|a\s+couple|a\s+drink|a\s+beer|a\s+glass|some\s+wine|champagne|alcohol|a\s+nurofen"
    rf"|a\s+paracetamol|a\s+tylenol|an\s+advil)",
    # "is there any harm in pausing", "would it really matter if I had champagne",
    # "is crushing my Seroquel okay", "would doubling my Prozac help", "okay if I don't start"
    r"\b(any|no)\s+harm\s+in\b|\b(would|does|will)\s+it\s+(really\s+)?matter\s+if\b",
    r"\b(is|would\s+be)\s+(crushing|splitting|halving|doubling|skipping|stopping|taking|having"
    r"|restarting|pausing|mixing|drinking)\b.{0,50}\b(ok|okay|alright|fine|safe|a\s+problem)",
    r"\bwould\s+(doubling|halving|stopping|skipping|taking|increasing|cutting)\b",
    rf"\b(ok|okay|alright|fine)\s+if\s+{_WHO}\b|\b(ok|okay|alright|fine|safe)\s+to\s+(have|eat)\b",
    rf"\b{_WHO}\s+(need|should\s+have|should\s+take)\s+(more|less|fewer)\s+than\b",
    r"\bis\s+(it|that)\s+(really\s+)?necessary\b|\bgood\s+idea\b",
    r"\bis\s+(the|my|this|that)\s+(\w+\s+){0,3}(tablet|pill|medicine|medication|capsule|syrup"
    r"|spray|inhaler|patch|cream)\s+(ok|okay|alright|safe|fine)\b",
    r"\bhow\s+(much|many)\s+\w+\s+for\b",
    # "do my fish oil capsules clash with warfarin"
    r"\b(clash|interact|interfere)\w*\s+with\b",
    # "how many advil is too many for me", "how much should I take"
    r"\bhow\s+(much|many)\b.{0,40}\b(should|can|could|do|to\s+take|is\s+(too|to)\s+(much"
    r"|many)|too\s+(much|many))\b",
))


def is_decision(question):
    """Whether a question asks for a decision about a dose - one for the prescriber, so
    answered by ask.decision() and never by a model."""
    q = plain(question)
    return any(p.search(q) for p in DECISION)


# ---- dose instructions in an answer -----------------------------------------------------

# What the model is told never to write, looked for in what it wrote. The single pattern
# this replaces needed "you" or "it" and a modal - "you can stop" - and caught almost none
# of the ways an instruction is actually phrased: "Stop the ibuprofen for now.", "It's safe
# to take them together.", "No need to keep taking the prednisone once the rash clears."
#
# A sentence that says where it comes from ("your prescription says to take...", "Dr Nguyen
# wrote that...") relays the record, which is the Companion's job, so it is left alone.
_IMPERATIVE = re.compile(
    r"(^|,\s+|:\s+|\s[\u2014\u2013-]\s+)(please\s+|just\s+|so\s+|then\s+|honestly\s+|now\s+)?("
    r"stop(?!\s+by)|start\s+(taking|using|on|the|your|it)|skip|take(?!\s+(a\s+look|note"
    r"|care|a\s+moment|a\s+photo|a\s+picture))|halve|cut|double|increase|decrease|reduce"
    r"|lower|raise|keep\s+(taking|using|on|it|them|the|going)|continue|stay\s+on|go\s+back"
    r"|go\s+ahead(?!\s+and\s+(ask|call|check|contact|talk|speak))|give\s+(him|her|them|it"
    r"|your\s+\w+\s+\d+)|hold\s+(off|the|your|it)|finish|crush|split|chew|mix|try(?!\s+("
    r"asking|calling|checking|contacting|speaking|talking|to\s+(ask|call|check|speak|talk)))"
    r"|restart|resume|drop|wean|come\s+off|carry\s+on|leave\s+out|pop|open|sprinkle"
    r"|feel\s+free\s+to(?!\s+("
    r"ask|upload|share|contact|reach)))\b")
_YOU_MAY = re.compile(
    r"\byou\b[^.?!]{0,30}?\b(can|could|should|may|might|might\s+want\s+to|may\s+want\s+to"
    r"|could\s+try|are\s+fine\s+to|'ll\s+be\s+fine|will\s+be\s+fine|are\s+(ok|okay|fine|safe)"
    r"\s+to)\s+(just\s+|safely\s+|still\s+|go\s+ahead\s+and\s+)?(stop|start|skip|double"
    r"|halve|increase|decrease|reduce|cut|split|combine|take|keep|continue|go\s+down|go\s+up"
    r"|going|skipping|stopping|taking|use|using|give|finish|try|drop|move|switch|swap|change"
    r"|have|drink|carry\s+on)\b")
_SAFE_CLAIM = re.compile(
    r"\b(is|are|'s|'re|be)\s+(absolutely\s+|perfectly\s+|generally\s+|totally\s+|still\s+"
    r"|completely\s+|usually\s+)?(fine|safe|ok|okay|alright|all\s+right|reasonable"
    r"|no\s+problem)\b")
_ABOUT_TAKING = re.compile(
    r"\b(tak|us|skip|stop|doubl|split|halv|continu|crush|chew|having|drink|wine|beer"
    r"|champagne|alcohol|together|dose|tablet|pill|capsule|puff|mg\b|course|instead|giv)\w*"
    r"|\bwith\s+(your|the|my|that)\b|\bfor\s+you\b|\b(a|per)\s+day\b|\bdaily\b")
_NO_NEED = re.compile(
    r"\b(no|there'?s\s+no|there\s+is\s+no)\s+(need|reason)\s+to\s+(keep|take|finish|continue"
    r"|use|stay|bother)|\bdon'?t\s+(worry\s+about|bother)\s+(finishing|taking|continuing"
    r"|using|with)")
_I_WOULD = re.compile(
    r"\b(i'?d|i\s+would|let'?s|we\s+(can|could|should))\s+(just\s+)?(stop|hold|take|skip"
    r"|cut|reduce|try|go|switch|start|keep|continue|drop|leave|ease)\b"
    # the assistant's own judgement, however softly put
    r"|\bit\s+would\s+be\s+(sensible|reasonable|wise|fine|ok|okay)\s+to\b"
    r"|\bsounds\s+like\s+a\s+(sensible|good|reasonable|fine)\s+(plan|idea)\b"
    r"|\b(the\s+)?(safer|sensible|better)\s+option\b"
    r"|\bmost\s+people\s+(in\s+your\s+\w+\s+)?(simply\s+|just\s+)?(stop|take|skip|halve|cut"
    r"|double|go|switch|start|continue|keep)\b"
    r"|\b(it'?s|it\s+is)\s+(common|normal|usual|standard)\s+to\s+(stop|take|skip|halve|cut"
    r"|double|split|crush|continue|keep|give)\b"
    r"|\b(won'?t|wouldn'?t|shouldn'?t|will\s+not)\s+(be\s+a\s+problem|cause\s+(you\s+)?"
    r"(any\s+)?(issues|problems|harm|trouble))|\bno\s+harm\s+in\b")
_RELAYED = re.compile(
    r"\b(says?|said|wrote|writes|according\s+to|per\s+(your|the)|instructions?|label"
    r"|leaflet|letter|summary|records?\s+(show|say)|notes?\s+(say|says|mention)"
    r"|as\s+prescribed|exactly\s+as)\b")
_UNDECIDED = re.compile(
    r"\b(whether|unless|not\s+sure|can'?t\s+say|don'?t\s+know|not\s+able|ask|check\s+with)\b")
_SENTENCES = re.compile(r"(?<=[.!?;])\s+|\n+")


def directs(answer):
    """Whether an answer tells somebody to start, stop, skip, change or keep taking a
    medicine, or says that doing so is safe for them."""
    for sentence in _SENTENCES.split(plain_keep_lines(answer)):
        s = sentence.strip()
        # The assistant's own opinion is never a relay of the record, even in a sentence
        # that mentions one: "your GP's letter mentions the dose went up, and I'd keep going".
        if _I_WOULD.search(s):
            return True
        if not s or _RELAYED.search(s):
            continue
        if _IMPERATIVE.search(s) or _YOU_MAY.search(s) or _NO_NEED.search(s):
            return True
        if _SAFE_CLAIM.search(s) and _ABOUT_TAKING.search(s) and not _UNDECIDED.search(s):
            return True
    return False
