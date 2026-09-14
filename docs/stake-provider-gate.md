# Porte de conformité du provider Stake

Cette page décrit le squelette historique `StakeAuthorizedProvider`. La demande
explicite de scraping sans API est désormais traitée par un [collecteur de pages
publiques distinct](stake-public-scraping.md), selon [ADR-0001](adr/0001-stake-public-dom-scraping.md).

`StakeAuthorizedProvider` est un `DisabledProvider`. Il ne contient aucun transport,
ne collecte aucune cote et publie toujours un état `unavailable` avec une explication
explicite.

Un [parcours séparé de relevés manuels](observed-odds.md) permet de conserver et
consulter des observations sous le code `stake-observed`. Il ne lève pas cette
porte, n'utilise pas ce connecteur et ne constitue pas un flux automatique.

`STAKE_PROVIDER_ENABLED`, `STAKE_WRITTEN_AUTHORIZATION_CONFIRMED`,
`STAKE_LAWFUL_JURISDICTION_CONFIRMED` et `STAKE_LEGAL_VALIDATION_CONFIRMED` valent
`false` par défaut. Le démarrage refuse l'activation si l'autorisation écrite du
fournisseur, la juridiction licite et la validation juridique ne sont pas toutes
confirmées. Même avec ces confirmations, il reste bloqué tant qu'une future
implémentation autorisée n'a pas fait l'objet d'une revue et d'un changement de code
explicite.

Le gate CI exécute `infra/scripts/check_provider_compliance.py`. Il inspecte les
sources exécutables et échoue sur les signatures de contournement documentées :
endpoint sur `stake.com`, solveur CAPTCHA, proxy résidentiel, contournement géographique,
réutilisation de cookies bookmaker, navigateur furtif et automatisation de mise.

La levée future de cette porte exigera donc simultanément :

1. une autorisation écrite couvrant l'accès automatisé et la réutilisation des cotes ;
2. une juridiction licite sans masquage géographique ;
3. une validation juridique couvrant l'usage et la redistribution ;
4. une implémentation revue, documentée et testée sans mécanisme de contournement.
