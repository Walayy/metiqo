# Import manuel de cotes

`ManualImportOddsProvider` accepte un document complet au format CSV UTF-8 ou une liste JSON. L'import est atomique : si une seule ligne est invalide, aucune observation du document ne devient visible. Chaque erreur contient le numéro de ligne, le champ, un code stable et un message.

La clé d'idempotence est `sha256:<digest>`, où `digest` est le SHA-256 des octets exacts du document, avant décodage. Réimporter les mêmes octets ne crée aucun événement, marché, sélection ou snapshot supplémentaire et retourne `duplicate=true`.

## Colonnes obligatoires

Le CSV doit utiliser exactement cet ordre. Chaque objet JSON doit contenir exactement les mêmes clés :

```text
provider,provider_event_id,game_title,competition,participant_a,participant_b,starts_at,best_of,event_status,provider_market_id,market_label,market_type,period,line,unit,provider_selection_id,selection,selection_label,decimal_odds,market_status,captured_at,timestamp_reliable,settlement_rules_version,remake_policy,forfeit_policy,cancelled_policy,provenance_reference
```

`starts_at` et `captured_at` sont des instants ISO 8601 avec fuseau. `decimal_odds` doit être fini et supérieur ou égal à 1. `provider` doit être le code logique donné au constructeur du provider. `unit` et les politiques `remake_policy`, `forfeit_policy`, `cancelled_policy` rendent la règle de marché vérifiable avant pricing. Chaque politique vaut `settle`, `void` ou `review`. Un timestamp déclaré non fiable reste importable pour diagnostic, mais chaque snapshot correspondant est forcé à `informational_only=true` et ne peut donc pas devenir un signal validé.
