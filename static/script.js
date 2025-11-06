const socket = io();
const board = document.getElementById("board");
if (board) socket.emit("join", { room: board.dataset.boardId });

// Drag and Drop Logic
document.querySelectorAll(".card").forEach(card => {
  card.addEventListener("dragstart", e => {
    e.dataTransfer.setData("card_id", card.dataset.cardId);
  });
});

document.querySelectorAll(".list .cards").forEach(list => {
  list.addEventListener("dragover", e => e.preventDefault());
  list.addEventListener("drop", e => {
    e.preventDefault();
    const cardId = e.dataTransfer.getData("card_id");
    const newListId = list.parentElement.dataset.listId;
    const card = document.querySelector(`[data-card-id='${cardId}']`);
    list.appendChild(card);
    socket.emit("move_card", { card_id: cardId, new_list_id: newListId });
  });
});

socket.on("card_moved", data => {
  const card = document.querySelector(`[data-card-id='${data.card_id}']`);
  const targetList = document.querySelector(`[data-list-id='${data.new_list_id}'] .cards`);
  if (card && targetList) targetList.appendChild(card);
});
