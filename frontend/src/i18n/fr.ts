import type { Messages } from "@/i18n/pt-PT";

// French, with "vous", as French business software is written.
// Typed as Messages: a missing or extra key fails the build.
export const fr: Messages = {
  product: "Enterprise Knowledge AI",
  productShort: "EKA",
  signIn: {
    title: "Les r\u00e9ponses de votre entreprise, sources \u00e0 l\u2019appui.",
    body: "Posez la question dont vous avez besoin. La r\u00e9ponse vient des documents auxquels vous avez acc\u00e8s, avec le passage exact dont elle est tir\u00e9e.",
    action: "Se connecter",
    note: "Vous vous connectez avec le compte de votre organisation.",
  },
  specimen: {
    label: "Exemple de r\u00e9ponse avec sa source",
    question: "Combien de jours de cong\u00e9s ai-je par an\u00a0?",
    answer: "Vous avez droit \u00e0 25 jours ouvr\u00e9s de cong\u00e9s par ann\u00e9e civile",
    source: "Guide du collaborateur",
    section: "1. Cong\u00e9s",
    quoted: (text: string) => `\u00ab\u00a0${text}\u00a0\u00bb`,
    passage: "Chaque collaborateur a droit \u00e0 25 jours ouvr\u00e9s de cong\u00e9s par ann\u00e9e civile.",
  },
  nav: {
    main: "Principal",
    assistant: "Assistant",
    signOut: "Se d\u00e9connecter",
    organization: "Organisation",
    switchOrganization: "Changer d\u2019organisation",
  },
  language: {
    label: "Langue de l\u2019interface",
    saved: "Langue modifi\u00e9e",
  },
  assistant: {
    title: "Assistant",
    placeholder: "Saisissez votre question, par exemple\u00a0: combien de jours de cong\u00e9s ai-je par an\u00a0?",
    ask: "Demander",
    asking: "Recherche et r\u00e9daction\u2026",
    hint: "Entr\u00e9e envoie la question. Maj+Entr\u00e9e passe \u00e0 la ligne.",
    emptyTitle: "Que souhaitez-vous savoir\u00a0?",
    emptyBody: "Les r\u00e9ponses citent le passage dont elles viennent. Si les documents auxquels vous avez acc\u00e8s ne r\u00e9pondent pas, je vous dis que je ne sais pas. Je n\u2019invente jamais.",
    sources: "Sources",
    source: (number: number) => `Source ${number}`,
    sourcesConsulted: "Consult\u00e9es, non cit\u00e9es",
    noAnswerTitle: "Pas de r\u00e9ponse fiable",
    verified: "V\u00e9rifi\u00e9e dans les sources",
    elapsed: (seconds: number) => `${seconds}\u00a0s`,
    errorTitle: "Impossible de r\u00e9pondre",
    errors: {
      unavailable: "Le mod\u00e8le de r\u00e9ponse n\u2019est pas disponible. V\u00e9rifiez qu\u2019il est lanc\u00e9 et r\u00e9essayez.",
      forbidden: "Vous n\u2019avez pas acc\u00e8s \u00e0 cette organisation.",
      invalid: "La question n\u2019est pas valide. \u00c9crivez entre 1 et 500 caract\u00e8res.",
      signedOut: "Votre session a expir\u00e9. Reconnectez-vous pour continuer.",
      network: "Impossible de joindre le serveur. V\u00e9rifiez votre connexion et r\u00e9essayez.",
      unknown: "Un probl\u00e8me est survenu de notre c\u00f4t\u00e9. R\u00e9essayez dans un instant.",
    },
    tryAgain: "R\u00e9essayer",
  },
  access: {
    signedOut: {
      title: "Votre session n\u2019a pas pu \u00eatre confirm\u00e9e",
      body: "Le serveur n\u2019a pas accept\u00e9 votre session. Reconnectez-vous pour continuer.",
      action: "Se reconnecter",
    },
    unverified: {
      title: "Confirmez votre adresse e-mail",
      body: "Seuls les comptes dont l\u2019adresse e-mail est confirm\u00e9e peuvent se connecter. Ouvrez le message de confirmation re\u00e7u, puis reconnectez-vous.",
      action: "Se reconnecter",
    },
    unavailable: {
      title: "Le service n\u2019est pas disponible",
      body: "Impossible de charger vos organisations. R\u00e9essayez dans un instant.",
      action: "R\u00e9essayer",
    },
  },
  noOrganization: {
    title: "Vous ne faites encore partie d\u2019aucune organisation",
    body: "Demandez \u00e0 un administrateur de votre entreprise de vous inviter. Une fois l\u2019invitation accept\u00e9e, l\u2019assistant sera disponible ici.",
  },
};
