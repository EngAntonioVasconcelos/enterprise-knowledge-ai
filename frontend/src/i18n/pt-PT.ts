// Every word the interface shows, in European Portuguese (tu). This file
// sets the shape: the other languages must have exactly the same keys,
// which TypeScript checks (see en.ts and fr.ts).
export const ptPT = {
  product: "Enterprise Knowledge AI",
  productShort: "EKA",
  signIn: {
    title: "Respostas da tua empresa, com as fontes \u00e0 vista.",
    body: "Pergunta o que precisas de saber. A resposta vem dos documentos a que tens acesso, com a passagem exata de onde saiu.",
    action: "Entrar",
    note: "Entras com a conta da tua organiza\u00e7\u00e3o.",
  },
  specimen: {
    label: "Exemplo de uma resposta com fonte",
    question: "Quantos dias de f\u00e9rias tenho por ano?",
    answer: "Tens direito a 25 dias \u00fateis de f\u00e9rias por ano civil",
    source: "Manual do Colaborador",
    section: "1. F\u00e9rias",
    quoted: (text: string) => `\u00ab${text}\u00bb`,
    passage: "Cada colaborador tem direito a 25 dias \u00fateis de f\u00e9rias por ano civil.",
  },
  nav: {
    main: "Principal",
    assistant: "Assistente",
    signOut: "Sair",
    organization: "Organiza\u00e7\u00e3o",
    switchOrganization: "Mudar de organiza\u00e7\u00e3o",
  },
  language: {
    label: "Idioma da interface",
    saved: "Idioma alterado",
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
    source: (number: number) => `Fonte ${number}`,
    sourcesConsulted: "Consultadas, n\u00e3o citadas",
    noAnswerTitle: "Sem resposta segura",
    verified: "Verificada nas fontes",
    elapsed: (seconds: number) => `${seconds} s`,
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
  access: {
    signedOut: {
      title: "N\u00e3o foi poss\u00edvel confirmar a tua sess\u00e3o",
      body: "O servidor n\u00e3o aceitou a tua sess\u00e3o. Entra de novo para continuar.",
      action: "Entrar de novo",
    },
    unverified: {
      title: "Confirma o teu e-mail",
      body: "S\u00f3 entram contas com o e-mail confirmado. Abre a mensagem de confirma\u00e7\u00e3o que recebeste e entra de novo.",
      action: "Entrar de novo",
    },
    unavailable: {
      title: "O servi\u00e7o n\u00e3o est\u00e1 dispon\u00edvel",
      body: "N\u00e3o foi poss\u00edvel carregar as tuas organiza\u00e7\u00f5es. Tenta de novo daqui a pouco.",
      action: "Tentar de novo",
    },
  },
  noOrganization: {
    title: "Cria a organiza\u00e7\u00e3o da tua empresa",
    body: "\u00c9 onde ficam os documentos e as pessoas com acesso a eles. Ficas como propriet\u00e1rio.",
    invited: "Se a tua empresa j\u00e1 usa o Enterprise Knowledge AI, n\u00e3o cries outra: pede a um administrador que te convide.",
  },
  onboarding: {
    nameLabel: "Nome da organiza\u00e7\u00e3o",
    nameHint: "Normalmente, o nome da empresa ou da equipa.",
    namePlaceholder: "Ex.: Atl\u00e2ntico Seguros",
    create: "Criar organiza\u00e7\u00e3o",
    creating: "A criar\u2026",
    errors: {
      invalid: "Escreve um nome entre 2 e 150 caracteres.",
      signedOut: "A tua sess\u00e3o terminou. Entra de novo e tenta outra vez.",
      unavailable: "N\u00e3o foi poss\u00edvel criar a organiza\u00e7\u00e3o. Tenta de novo daqui a pouco.",
    },
  },
};

export type Messages = typeof ptPT;
