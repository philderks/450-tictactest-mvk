package ch.bbw.m450.tictactoe.players;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import ch.bbw.m450.tictactoe.TicTacToeMain;
import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import org.junit.jupiter.api.Test;
import org.junitpioneer.jupiter.StdIo;
import org.junitpioneer.jupiter.StdOut;

class HumanPlayerTest {

	@Test
	void play_readsConsecutiveMoves_whenAllInputIsAvailableAtOnce() {
		var input = new ByteArrayInputStream("4\n8\n".getBytes(StandardCharsets.UTF_8));
		var player = new HumanPlayer(input);
		var board = new Stone[TicTacToeMain.BOARD_SIZE];

		var first = player.play(board, Stone.CROSS);
		var second = player.play(board, Stone.CROSS);

		assertThat(first).as("first move").isEqualTo(4);
		assertThat(second).as("second move").isEqualTo(8);
	}

	@Test
	@StdIo({"4", "8"})
	void play_readsStdIn_andPrintsPromptForEachMove(StdOut out) {
		var player = new HumanPlayer();
		var board = new Stone[TicTacToeMain.BOARD_SIZE];

		assertThat(player.play(board, Stone.CROSS)).isEqualTo(4);
		assertThat(player.play(board, Stone.CIRCLE)).isEqualTo(8);

		assertThat(out.capturedLines())
				.filteredOn(line -> line.contains("where to to put the next"))
				.containsExactly(
						"where to to put the next CROSS? (0-8): ",
						"where to to put the next CIRCLE? (0-8): ");
	}
}
