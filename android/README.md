# Nexus Sports pour Android

Application Android native Kotlin/Jetpack Compose dédiée aux paris sportifs. Le trading et le pont Windows restent hors de ce module.

## Ouvrir dans Android Studio

Ouvre ce dossier `android/` dans Android Studio. Le projet utilise Android Gradle Plugin 9.4.1, Gradle 9.6.0, Kotlin 2.4.10, Jetpack Compose BOM 2026.09.00 et Android SDK 37. Android Studio téléchargera les composants et bibliothèques manquants lors de la synchronisation Gradle.

L’application contient un écran Android natif pour le catalogue. « Ouvrir » lance le bookmaker installé quand il est reconnu; sinon l’action ouvre Google Play. Pour les opérateurs distribués en APK, l’action ouvre la page officielle de l’opérateur. L’onglet Nexus IA affiche l’interface de Nexus hébergée sur Render; le backend reste côté serveur, les clés des fournisseurs ne sont pas copiées dans l’application.

Les liens d’installation sont ceux des fiches officielles Google Play ou des pages de téléchargement des opérateurs. La disponibilité varie selon le pays. Les intégrations actuelles ouvrent les applications et ne placent pas de paris.
