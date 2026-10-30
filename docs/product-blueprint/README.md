# Specifiche tecniche legacy — consultazione su richiesta

Questa cartella contiene soltanto i dettagli ancora potenzialmente utilizzabili per i **193 requisiti identificati da `NL-BP-*`**, l'indice macchina `INDEX.json` non alterato, due addenda con contenuti non tutti riprodotti nelle specifiche e tre template. I vecchi `MASTER_INDEX`, `MASTER_CHECKLIST`, handoff, changelog, prompt, manifest di snapshot e note d'importazione **non sono più autorevoli**: ora esiste un solo piano 1.0 alla radice di `docs`.

L'indice JSON è preservato per compatibilità con il planner, ma i campi `source_inventory`, `dedup_map` e riferimenti storici possono citare documenti che ora si trovano **nell'archivio degli esclusi**. Non riscrivere gli ID o i punteggi per aggiornare il layout: verificare prima eventuali consumatori nel codice.

Non caricare tutta questa raccolta in un prompt; aprire soltanto le SPEC specifiche del requisito attivo.
