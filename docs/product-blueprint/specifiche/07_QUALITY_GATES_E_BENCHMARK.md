# SPEC-07 — Maximum Verified Quality: prove prima delle opinioni

**Principio:** “Un risultato verificato vale più di dieci pareri concordi di altri agenti.”

Criteri: corretta implementazione requisiti osservabili, test appropriati, regressioni, build, type check/static analysis dove applicabile, sicurezza dipendenze/scope, maintainability, integrazione. La review umana/model-based dà valutazioni argomentate, non un sigillo matematico.

La pipeline non conclude in caso di: test fallito, diff vuoto quando era richiesta modifica, tool call non attribuibili, gate obbligatori mancanti, reviewer reject, violazione scope, cambio non verificato, manual check non eseguito. Evitare test che verificano solo la stessa assunzione hardcoded dal Developer. Per bug UI/hardware prevedere screenshot o test native/manuali con stati chiari; non fingere prova con semplice pytest.

Un test può passare ma non coprire il requisito: reviewer controlla matrice requisito→prova e rischi. Un reviewer può rifiutare anche con test green, purché riporti problemi riproducibili o motivazioni. Se reviewer approva ma test fail, fail vince.

Misure storiche granulari per modello e ruolo; criteri di comparabilità hardware/tempo/lunghezza input/versione; nessuna classifica universale fittizia. Retry e escalation motivati, bounded e senza looping su stessa firma errore; il goal non si completa se solo le caselle TODO sono spuntate.

**Accettazione:** introdurre test con failure noto e review positiva simulata; completamento deve essere bloccato. Con task senza errori, prove e verdict devono restare consultabili dopo restart.
