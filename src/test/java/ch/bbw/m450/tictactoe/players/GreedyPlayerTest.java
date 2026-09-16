package ch.bbw.m450.tictactoe.players;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ch.bbw.m450.tictactoe.TicTacToeMain;
import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import org.junit.jupiter.api.Test;

class GreedyPlayerTest {

	@Test
	void play_throwsIllegalStateException_whenBoardIsFull() {
		var board = new Stone[TicTacToeMain.BOARD_SIZE];
		for (var i = 0; i < board.length; i++) {
			board[i] = i % 2 == 0 ? Stone.CROSS : Stone.CIRCLE;
		}
		var player = new GreedyPlayer();

		assertThatThrownBy(() -> player.play(board, Stone.CROSS))
				.isInstanceOf(IllegalStateException.class);
	}
}
