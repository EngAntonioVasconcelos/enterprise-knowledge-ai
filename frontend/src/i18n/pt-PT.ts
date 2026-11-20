// Every word the interface shows, in European Portuguese (tu). Kept in one
// place so wording stays consistent and a second language is a new file.
export const messages = {
  product: "Enterprise Knowledge AI",
  productShort: "EKA",
  signIn: {
    title: "Respostas da tua empresa, com as fontes \u00e0 vista.",
    body: "Pergunta o que precisas de saber. A resposta vem dos documentos a que tens acesso, com a passagem exata de onde saiu.",
    action: "Entrar",
    note: "Entras com a conta da tua organiza\u00e7\u00e3o.",
  },
  nav: {
    assistant: "Assistente",
    signOut: "Sair",
    organization: "Organiza\u00e7\u00e3o",
    switchOrganization: "Mudar de organiza\u00e7\u00e3o",
  },
  assistant: {
    title: "Assistente",
    placeholder: "Escreve a tua pergunta, por exemplo: quantos dias de f\u00e9rias tenho por ano?",
    ask: "Perguntar",
    asking: "A procurar e a escrever\u2026",
    hint: "Enter envia a pergunta. Shift+Enter muda de linha.",
    emptyTitle: "O que precisas de saber?",
    emptyBody: "As respostas citam a passagem de onde v\u00eam. Se os documentos a que tens acesso n\u00e3o responderem, digo-te que n\u00e3o sei. Nunca invento.",
    sources: "Fontes",
    sourcesConsulted: "Consultadas, n\u00e3o citadas",
    noAnswerTitle: "Sem resposta segura",
    verified: "Verificada nas fontes",
    elapsed: (seconds: number) => `${seconds} s`,
    section: "Sec\u00e7\u00e3o",
    errorTitle: "N\u00e3o foi poss\u00edvel responder",
    errors: {
      unavailable: "O modelo de respostas n\u00e3o est\u00e1 dispon\u00edvel. Confirma que est\u00e1 ligado e tenta de novo.",
      forbidden: "N\u00e3o tens acesso a esta organiza\u00e7\u00e3o.",
      invalid: "A pergunta n\u00e3o \u00e9 v\u00e1lida. Escreve entre 1 e 500 caracteres.",
      signedOut: "A tua sess\u00e3o terminou. Entra de novo para continuar.",
      network: "N\u00e3o foi poss\u00edvel contactar o servidor. Verifica a liga\u00e7\u00e3o e tenta de novo.",
      unknown: "Algo correu mal do nosso lado. Tenta de novo daqui a pouco.",
    },
    tryAgain: "Tentar de novo",
  },
  noOrganization: {
    title: "Ainda n\u00e3o pertences a nenhuma organiza\u00e7\u00e3o",
    body: "Pede a um administrador da tua empresa que te convide. Quando aceitares o convite, o assistente fica dispon\u00edvel aqui.",
  },
} as const;

export type Messages = typeof messages;
