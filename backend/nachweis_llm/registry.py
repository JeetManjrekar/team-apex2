from __future__ import annotations

from dataclasses import dataclass

from .domain import DocumentType


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    label_de: str
    question_de: str
    required: bool = False


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    document_type: DocumentType
    title_de: str
    description_de: str
    fields: tuple[FieldSpec, ...]

    @property
    def required_fields(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields if field.required)

    @property
    def field_names(self) -> set[str]:
        return {field.name for field in self.fields}


DOCUMENT_REGISTRY: dict[DocumentType, DocumentSpec] = {
    DocumentType.NACHTRAGSMELDUNG: DocumentSpec(
        document_type=DocumentType.NACHTRAGSMELDUNG,
        title_de="Nachtragsmeldung - Dokumentationsentwurf",
        description_de="Interne sachliche Dokumentation eines moeglichen zusaetzlichen oder geaenderten Leistungsumfangs.",
        fields=(
            FieldSpec("project", "Projekt", "Wie lautet die Projektbezeichnung?", True),
            FieldSpec("location", "Ort / Bauteil", "An welcher Stelle ist der Sachverhalt aufgetreten?", True),
            FieldSpec("event_datetime", "Datum und Uhrzeit", "Wann wurde der Sachverhalt festgestellt?", True),
            FieldSpec("description", "Sachverhalt", "Was wurde vor Ort konkret festgestellt oder ausgefuehrt?", True),
            FieldSpec("instruction_by", "Anordnung durch", "Wer hat die zusaetzliche oder geaenderte Leistung angeordnet?"),
            FieldSpec("instruction_datetime", "Zeitpunkt der Anordnung", "Wann erfolgte die Anordnung?"),
            FieldSpec("tender_reference", "Bezug zum Leistungsverzeichnis", "Welche Position oder welcher Leistungsumfang ist betroffen?"),
            FieldSpec("staff_hours", "Personal und Stunden", "Welche Mitarbeitenden oder Gewerke und Stunden sind dokumentiert?"),
            FieldSpec("equipment", "Geraete", "Welche Geraete waren beteiligt und welche Einsatzzeiten sind belegt?"),
            FieldSpec("material", "Material", "Welches Material war betroffen oder zusaetzlich erforderlich?"),
            FieldSpec("expected_ground", "Erwarteter Baugrund", "Welche Bodenverhaeltnisse nennt das Baugrundgutachten?"),
            FieldSpec("expected_ground_page", "Fundstelle im Gutachten", "Auf welcher Seite des Baugrundgutachtens steht diese Angabe?"),
            FieldSpec("found_ground", "Angetroffener Baugrund", "Welche Bodenverhaeltnisse wurden tatsaechlich angetroffen?"),
            FieldSpec("drilling_times", "Bohrzeiten", "Welche Bohrzeiten sind je Pfahl dokumentiert?"),
            FieldSpec("drilling_log", "Bohrprotokoll", "Liegt ein Bohrprotokoll vor bzw. wo ist es abgelegt?"),
            FieldSpec("related_instruction", "Zugehoerige Anweisung / E-Mail", "Gibt es eine zugehoerige Anweisung oder E-Mail des Bauherrn?"),
            FieldSpec("photo_evidence", "Fotobelege", "Welche Fotos dokumentieren den Sachverhalt?"),
        ),
    ),
    DocumentType.BAUTAGESBERICHT: DocumentSpec(
        document_type=DocumentType.BAUTAGESBERICHT,
        title_de="Bautagesbericht - Entwurf",
        description_de="Sachlicher Tagesbericht aus belegten Baustelleninformationen.",
        fields=(
            FieldSpec("date", "Berichtsdatum", "Fuer welches Datum gilt der Bautagesbericht?", True),
            FieldSpec("weather", "Wetter", "Wie waren die dokumentierten Wetterbedingungen?"),
            FieldSpec("temperature", "Temperatur", "Welche Temperatur ist dokumentiert?"),
            FieldSpec("staff_by_company_trade", "Personal je Firma / Gewerk", "Wie viele Personen waren je Firma und Gewerk vor Ort?"),
            FieldSpec("equipment", "Geraete", "Welche Geraete waren im Einsatz?"),
            FieldSpec("work_performed", "Ausgefuehrte Arbeiten", "Welche Arbeiten wurden ausgefuehrt?", True),
            FieldSpec("deliveries", "Lieferungen", "Welche Lieferungen sind eingetroffen oder waren unvollstaendig?"),
            FieldSpec("visits_inspections", "Besuche und Kontrollen", "Welche Besuche, Abnahmen oder Kontrollen fanden statt?"),
            FieldSpec("obstructions_incidents", "Behinderungen und Ereignisse", "Welche Behinderungen oder Ereignisse sind dokumentiert?"),
            FieldSpec("instructions", "Anweisungen", "Welche Anweisungen wurden erteilt?"),
            FieldSpec("photo_captions", "Fotodokumentation", "Welche Fotos gehoeren zu welchen Arbeiten oder Ereignissen?"),
            FieldSpec("signature", "Unterschrift", "Wer soll den Bericht pruefen bzw. unterschreiben?"),
        ),
    ),
    DocumentType.BEHINDERUNGSANZEIGE: DocumentSpec(
        document_type=DocumentType.BEHINDERUNGSANZEIGE,
        title_de="Behinderungsanzeige - Entwurf",
        description_de="Sachliche Erfassung einer gemeldeten Behinderung; keine rechtliche Bewertung.",
        fields=(
            FieldSpec("project", "Projekt", "Wie lautet die Projektbezeichnung?", True),
            FieldSpec("location", "Ort / Bauteil", "Wo tritt die Behinderung auf?", True),
            FieldSpec("event_datetime", "Beginn der Behinderung", "Seit wann besteht die Behinderung?", True),
            FieldSpec("obstruction_description", "Beschreibung", "Was ist die konkrete Ursache oder Beschreibung der Behinderung?", True),
            FieldSpec("affected_activity", "Betroffene Taetigkeit", "Welche Arbeiten sind betroffen?", True),
            FieldSpec("impact_on_work", "Auswirkung auf die Arbeiten", "Welche Auswirkungen sind bereits dokumentiert?"),
            FieldSpec("expected_duration", "Voraussichtliche Dauer", "Wie lange wird die Behinderung voraussichtlich dauern?"),
            FieldSpec("instruction_by", "Ansprechpartner / Verursacher", "Wer hat die Information gemeldet oder die Anweisung erteilt?"),
            FieldSpec("evidence", "Belege", "Welche Fotos, Berichte oder E-Mails belegen den Vorgang?"),
        ),
    ),
    DocumentType.MEHRKOSTENANZEIGE: DocumentSpec(
        document_type=DocumentType.MEHRKOSTENANZEIGE,
        title_de="Mehrkostenanzeige - Entwurf",
        description_de="Sachliche Dokumentation eines gemeldeten moeglichen Mehraufwands; keine Preisermittlung.",
        fields=(
            FieldSpec("project", "Projekt", "Wie lautet die Projektbezeichnung?", True),
            FieldSpec("location", "Ort / Bauteil", "Wo ist der Mehraufwand aufgetreten?", True),
            FieldSpec("event_datetime", "Datum und Uhrzeit", "Wann wurde der Mehraufwand festgestellt?", True),
            FieldSpec("description", "Sachverhalt", "Welcher Mehraufwand wurde konkret festgestellt?", True),
            FieldSpec("cause", "Ursache", "Welche Ursache ist durch die Unterlagen belegt?", True),
            FieldSpec("additional_effort", "Zusaetzlicher Aufwand", "Welche zusaetzlichen Stunden, Mengen oder Geraetezeiten sind belegt?"),
            FieldSpec("instruction_by", "Anordnung durch", "Wer hat den Vorgang angeordnet oder bestaetigt?"),
            FieldSpec("evidence", "Belege", "Welche Fotos, Protokolle oder E-Mails belegen den Vorgang?"),
        ),
    ),
    DocumentType.MAENGELANZEIGE: DocumentSpec(
        document_type=DocumentType.MAENGELANZEIGE,
        title_de="Maengelanzeige - Entwurf",
        description_de="Sachliche Erfassung eines beobachteten Mangels.",
        fields=(
            FieldSpec("project", "Projekt", "Wie lautet die Projektbezeichnung?", True),
            FieldSpec("location", "Ort / Bauteil", "Wo befindet sich der festgestellte Mangel?", True),
            FieldSpec("event_datetime", "Feststellungszeitpunkt", "Wann wurde der Mangel festgestellt?", True),
            FieldSpec("defect_description", "Mangelbeschreibung", "Was wurde konkret beobachtet?", True),
            FieldSpec("affected_trade", "Betroffenes Gewerk", "Welches Gewerk ist betroffen?"),
            FieldSpec("responsible_party", "Zustaendige Firma", "Welche Firma ist laut Unterlagen zustaendig?"),
            FieldSpec("evidence", "Belege", "Welche Fotos oder Pruefprotokolle dokumentieren den Mangel?"),
            FieldSpec("measure_taken", "Bisherige Massnahmen", "Welche Massnahmen wurden bereits dokumentiert?"),
        ),
    ),
    DocumentType.BEDENKENANMELDUNG: DocumentSpec(
        document_type=DocumentType.BEDENKENANMELDUNG,
        title_de="Bedenkenanmeldung - Entwurf",
        description_de="Sachliche Dokumentation angemeldeter technischer oder ausfuehrungsbezogener Bedenken.",
        fields=(
            FieldSpec("project", "Projekt", "Wie lautet die Projektbezeichnung?", True),
            FieldSpec("location", "Ort / Bauteil", "Auf welchen Ort oder Bauteil beziehen sich die Bedenken?", True),
            FieldSpec("event_datetime", "Datum", "Wann wurden die Bedenken festgestellt oder mitgeteilt?", True),
            FieldSpec("concern_description", "Bedenken", "Welche konkreten Bedenken wurden geaeussert?", True),
            FieldSpec("technical_basis", "Technische Grundlage", "Welche Unterlage oder Beobachtung stuetzt die Bedenken?"),
            FieldSpec("proposed_clarification", "Offene Klaerung", "Welche Klaerung oder Rueckmeldung wird benoetigt?"),
            FieldSpec("evidence", "Belege", "Welche Dokumente, Fotos oder E-Mails liegen dazu vor?"),
        ),
    ),
    DocumentType.AKTENNOTIZ: DocumentSpec(
        document_type=DocumentType.AKTENNOTIZ,
        title_de="Aktennotiz - Entwurf",
        description_de="Neutrale interne Notiz zu einem Baustellenvorgang.",
        fields=(
            FieldSpec("date", "Datum", "Wann fand der Vorgang statt?", True),
            FieldSpec("location", "Ort", "Wo fand der Vorgang statt?"),
            FieldSpec("participants", "Beteiligte", "Wer war beteiligt?"),
            FieldSpec("subject", "Betreff", "Worum ging es?", True),
            FieldSpec("facts", "Feststellungen", "Welche Tatsachen wurden festgehalten?", True),
            FieldSpec("next_steps", "Naechste Schritte", "Welche naechsten Schritte wurden vereinbart?"),
            FieldSpec("evidence", "Belege", "Welche Quellen gehoeren zur Notiz?"),
        ),
    ),
}

PHOTO_CATEGORIES: tuple[str, ...] = (
    "progress",
    "delivery",
    "defect",
    "nachtrag_evidence",
    "obstruction",
    "safety",
)
