import React from 'react';
import styles from './styles.module.css';

/**
 * Mockup de uma conversa do Telegram — não usa o logo oficial, só o estilo
 * visual de bolha de mensagem e a paleta de cor característica do app.
 */
export default function ChatBubble({texto, autor, horario = '08:00', botNome = 'Frase Diária'}) {
  return (
    <div className={styles.phone}>
      <div className={styles.header}>
        <div className={styles.avatar} aria-hidden="true">
          💬
        </div>
        <div className={styles.headerText}>
          <span className={styles.headerName}>{botNome}</span>
          <span className={styles.headerStatus}>bot</span>
        </div>
      </div>
      <div className={styles.body}>
        <div className={styles.bubble}>
          {texto}
          {autor ? <span className={styles.author}>— {autor}</span> : null}
          <span className={styles.time}>{horario}</span>
        </div>
      </div>
    </div>
  );
}
